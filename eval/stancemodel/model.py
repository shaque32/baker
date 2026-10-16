"""The small stance model: a multilingual encoder with a 4-way stance head and a quote-span head.

Arm 1 of Baker's own stance model (eval/stancedata/README.md). The encoder is a local copy of
microsoft/mdeberta-v3-base (MIT). The stance head reads the first token; the span head scores
each token of the record's text as the quote's first or last token, so a quote can only be a
piece of the record. The word embeddings stay frozen: they are a third of the weights, and
freezing them keeps words the training data never shows where the base model put them.

Loading never touches the network: every path is a local directory.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import torch
from torch import nn

from eval.stancemodel.encode import LABELS, NO_SPAN, Encoded

MODEL_FILE = "model.safetensors"
META_FILE = "stancemodel.json"
NEG = -1e4


class StanceModel(nn.Module):
    def __init__(self, encoder: nn.Module, dropout: float = 0.1) -> None:
        super().__init__()
        self.encoder = encoder
        hidden = encoder.config.hidden_size
        self.pool = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, hidden), nn.GELU())
        self.stance = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, len(LABELS)))
        self.span = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 2))

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor, record_mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        h = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        logits = self.stance(self.pool(h[:, 0]))
        start, end = self.span(h).unbind(-1)
        start = start.masked_fill(~record_mask, NEG)
        end = end.masked_fill(~record_mask, NEG)
        return logits, start, end


def load_encoder(base_dir: Path) -> nn.Module:
    from transformers import AutoConfig, AutoModel

    config = AutoConfig.from_pretrained(base_dir, local_files_only=True)
    return AutoModel.from_pretrained(
        base_dir, config=config, dtype=torch.float32, local_files_only=True
    )


def new_model(base_dir: Path, dropout: float = 0.1) -> StanceModel:
    model = StanceModel(load_encoder(base_dir), dropout=dropout)
    model.encoder.embeddings.word_embeddings.weight.requires_grad_(False)
    return model


def trainable_state(model: nn.Module) -> dict[str, torch.Tensor]:
    """Every trained weight; the frozen ones come back from the base model."""
    return {n: p.detach().clone() for n, p in model.named_parameters() if p.requires_grad}


def collate(batch: Sequence[Encoded], pad_id: int) -> dict[str, torch.Tensor]:
    n = max(len(e.input_ids) for e in batch)
    ids = torch.full((len(batch), n), pad_id, dtype=torch.long)
    att = torch.zeros((len(batch), n), dtype=torch.long)
    rec = torch.zeros((len(batch), n), dtype=torch.bool)
    for i, e in enumerate(batch):
        k = len(e.input_ids)
        ids[i, :k] = torch.tensor(e.input_ids)
        att[i, :k] = 1
        rec[i, :k] = torch.tensor(e.record_mask)
    out = {"input_ids": ids, "attention_mask": att, "record_mask": rec}
    if all(e.label is not None for e in batch):
        out["labels"] = torch.tensor([e.label for e in batch])
        out["span_start"] = torch.tensor([e.span_start for e in batch])
        out["span_end"] = torch.tensor([e.span_end for e in batch])
    return out


def loss_sums(
    logits: torch.Tensor,
    start: torch.Tensor,
    end: torch.Tensor,
    batch: dict[str, torch.Tensor],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Summed stance loss over the items, and summed span loss over the items that have a
    quote (the mean of its start and end losses), so micro-batches add up to one batch. A
    "weights" entry in the batch scales each item's stance loss."""
    per_item = nn.functional.cross_entropy(logits, batch["labels"], reduction="none")
    if "weights" in batch:
        per_item = per_item * batch["weights"]
    stance = per_item.sum()
    has_span = batch["span_start"] != NO_SPAN
    if has_span.any():
        span = 0.5 * (
            nn.functional.cross_entropy(
                start[has_span], batch["span_start"][has_span], reduction="sum"
            )
            + nn.functional.cross_entropy(
                end[has_span], batch["span_end"][has_span], reduction="sum"
            )
        )
    else:
        span = logits.new_zeros(())
    return stance, span


def micro_batches(idx: Sequence[int], lengths: Sequence[int], max_tokens: int) -> list[list[int]]:
    """Split one batch into pieces of at most max_tokens padded tokens each (memory bound);
    the gradients of the pieces add up to the whole batch's."""
    out: list[list[int]] = []
    cur: list[int] = []
    for i in sorted(idx, key=lambda i: lengths[i]):
        if cur and (len(cur) + 1) * lengths[i] > max_tokens:
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


@torch.no_grad()
def score_items(
    model: StanceModel, encs: Sequence[Encoded], pad_id: int, batch_size: int = 32
) -> list[dict[str, Any]]:
    """Per item: the four stance probabilities and the start and end scores of every token."""
    model.eval()
    order = sorted(range(len(encs)), key=lambda i: len(encs[i].input_ids))
    out: list[dict[str, Any]] = [{} for _ in encs]
    for b in range(0, len(order), batch_size):
        idx = order[b : b + batch_size]
        batch = collate([encs[i] for i in idx], pad_id)
        logits, start, end = model(
            batch["input_ids"], batch["attention_mask"], batch["record_mask"]
        )
        probs = torch.softmax(logits, dim=-1)
        for row, i in enumerate(idx):
            k = len(encs[i].input_ids)
            out[i] = {
                "probs": {s: float(probs[row, j]) for j, s in enumerate(LABELS)},
                "start": start[row, :k].tolist(),
                "end": end[row, :k].tolist(),
            }
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(model: StanceModel, tok: Any, out_dir: Path, meta: dict[str, Any]) -> str:
    """Write one self-contained model folder; return the model file's SHA-256.

    Weights are stored as float16, as the base checkpoint is, and computed in float32 after
    loading. Every score that decides anything is made from this file, never from the model
    in memory during training.
    """
    from safetensors.torch import save_file

    out_dir.mkdir(parents=True, exist_ok=True)
    state = {
        k: (v.half() if v.is_floating_point() else v).contiguous()
        for k, v in model.state_dict().items()
    }
    save_file(state, str(out_dir / MODEL_FILE), metadata={"format": "pt"})
    model.encoder.config.save_pretrained(out_dir)
    tok.save_pretrained(out_dir)
    digest = sha256_file(out_dir / MODEL_FILE)
    meta = {**meta, "model_file": MODEL_FILE, "model_sha256": digest}
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return digest


def load_exported(model_dir: Path) -> tuple[StanceModel, Any, dict[str, Any]]:
    """Load an exported folder: the model, its tokenizer and its metadata. Local files only."""
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoModel, AutoTokenizer

    meta = json.loads((model_dir / META_FILE).read_text(encoding="utf-8"))
    config = AutoConfig.from_pretrained(model_dir, local_files_only=True)
    encoder = AutoModel.from_config(config, dtype=torch.float32)
    model = StanceModel(encoder, dropout=meta.get("dropout", 0.1))
    state = load_file(str(model_dir / MODEL_FILE))
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        raise ValueError(f"model file does not match: missing {missing}, unexpected {unexpected}")
    tok = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model.eval()
    return model, tok, meta
