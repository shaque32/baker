"""Train the small stance model on CPU, in chunks that stop and resume.

    python -m eval.stancemodel.train --base <local mdeberta-v3-base dir> \
        --train eval/out/stancedata/train.jsonl --dev eval/out/stancedata/heldout_dev.jsonl \
        --run eval/out/stancemodel/<run> [--budget-min 105]

Run the same command again to continue: it resumes from <run>/last.pt at the exact batch it
stopped at (the batch order is fixed by the seed). It exits 0 when training is done and the
exported model is in <run>/final, and 75 when it stopped at the time budget with work left.

Only the training split (ids T...) is trained on. The dev split (ids D...) is scored during
training, for watching and for tuning; the held-out test split and the probe set are never read
here. SYNTHETIC data only; no network: the base model is a local folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import torch

from eval.stancedata.chat import read_jsonl, sha256_file
from eval.stancedata.score import score
from eval.stancemodel import features
from eval.stancemodel.encode import NO_SPAN, Encoded, encode
from eval.stancemodel.model import (
    collate,
    export,
    loss_sums,
    micro_batches,
    new_model,
    score_items,
    trainable_state,
)
from eval.stancemodel.policy import Policy
from eval.stancemodel.predict import label_items, write_jsonl

EXIT_PAUSED = 75
BASE_MODEL = "microsoft/mdeberta-v3-base"
BASE_REVISION = "a0484667b22365f84929a935b5e50a51f71f159d"


def batch_plan(lengths: Sequence[int], batch: int, epochs: int, seed: int) -> list[list[int]]:
    """Every batch of every epoch, in order. Items of similar length share a batch (less
    padding); the order of batches is shuffled per epoch. Fixed by the seed."""
    plan: list[list[int]] = []
    for ep in range(epochs):
        rng = random.Random(seed * 1000 + ep)  # noqa: S311 - data order, not security
        idx = list(range(len(lengths)))
        rng.shuffle(idx)
        pool = batch * 50
        batches = []
        for c in range(0, len(idx), pool):
            chunk = sorted(idx[c : c + pool], key=lambda i: lengths[i])
            batches += [chunk[b : b + batch] for b in range(0, len(chunk), batch)]
        rng.shuffle(batches)
        plan += batches
    return plan


def plan_digest(plan: list[list[int]]) -> str:
    return hashlib.sha256(json.dumps(plan).encode()).hexdigest()[:16]


def lr_at(step: int, total: int, warmup: int) -> float:
    if step < warmup:
        return (step + 1) / warmup
    return max(0.0, (total - step) / max(1, total - warmup))


def evaluate(
    model: Any, encs: Sequence[Encoded], items: list[dict], pad_id: int, out: Path
) -> dict[str, Any]:
    scores = score_items(model, encs, pad_id, batch_size=16)
    rows = label_items(encs, scores, Policy())
    write_jsonl(rows, out)
    res = score(items, {r["probe_id"]: r for r in rows})["undisputed"]
    correct = sum(r["stance"] == it["gold_stance"] for r, it in zip(rows, items, strict=True))
    keys = ("n", "supports_recall", "contradicts_precision", "contradicts_recall",
            "contradicts_shown_as_supports", "overreach_shown_as_supports",
            "expert_load_precision", "passes_all")  # fmt: skip
    return {"accuracy": correct / len(rows), **{k: res.get(k) for k in keys}}


def save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    torch.save(state, tmp)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True, help="local mdeberta-v3-base folder")
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--train-sha256", default=None, help="refuse any other training file")
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--warmup", type=float, default=0.06)
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--span-weight", type=float, default=0.5)
    ap.add_argument(
        "--trap-weight", type=float, default=1.0,
        help="scale the stance loss of trap items (items whose trap field is set)",
    )  # fmt: skip
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--max-len", type=int, default=384)
    ap.add_argument("--max-tokens", type=int, default=2048, help="padded tokens per micro-batch")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--budget-min", type=float, default=105.0)
    ap.add_argument("--ckpt-every", type=int, default=100)
    ap.add_argument("--eval-every", type=int, default=250)
    ap.add_argument("--limit", type=int, default=0, help="train on the first N items (smoke test)")
    ap.add_argument("--dev-limit", type=int, default=0, help="score the first N dev items")
    ap.add_argument(
        "--init", type=Path, default=None,
        help="start from the weights of another run's checkpoint (last.pt or epochN.pt) "
        "with a fresh optimizer and schedule",
    )  # fmt: skip
    args = ap.parse_args(argv)

    t_start = time.time()
    torch.set_num_threads(args.threads)
    args.run.mkdir(parents=True, exist_ok=True)
    log_path = args.run / "log.jsonl"

    def log(row: dict[str, Any]) -> None:
        row = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row}
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)

    train_sha = sha256_file(args.train)
    if args.train_sha256 and train_sha != args.train_sha256:
        raise SystemExit(f"training file sha256 {train_sha} is not {args.train_sha256}")
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(args.base, local_files_only=True)
    train_items = read_jsonl(args.train)
    if any(not it["probe_id"].startswith("T") for it in train_items):
        raise SystemExit("the training file holds non-training ids")
    if args.limit:
        train_items = train_items[: args.limit]
    dev_items = read_jsonl(args.dev)
    if any(not it["probe_id"].startswith("D") for it in dev_items):
        raise SystemExit("the dev file holds non-dev ids")
    if args.dev_limit:
        dev_items = dev_items[: args.dev_limit]
    train_enc = [encode(it, tok, args.max_len) for it in train_items]
    dev_enc = [encode(it, tok, args.max_len) for it in dev_items]
    lengths = [len(e.input_ids) for e in train_enc]
    item_weight = [args.trap_weight if it.get("trap") else 1.0 for it in train_items]
    plan = batch_plan(lengths, args.batch, args.epochs, args.seed)
    total = len(plan)
    per_epoch = math.ceil(len(train_enc) / args.batch)
    warmup = max(1, int(total * args.warmup))

    torch.manual_seed(args.seed)
    model = new_model(args.base, dropout=args.dropout)
    decay, no_decay = [], []
    for name, p in model.named_parameters():
        if p.requires_grad:
            (no_decay if p.ndim < 2 or "LayerNorm" in name else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": args.weight_decay},
         {"params": no_decay, "weight_decay": 0.0}],
        lr=args.lr,
    )  # fmt: skip
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: lr_at(s, total, warmup))
    config = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}
    config.update(train_sha256=train_sha, plan=plan_digest(plan), total_steps=total,
                  features=features.VERSION)  # fmt: skip
    if args.init:
        config["init_sha256"] = sha256_file(args.init)

    step = 0
    ckpt = args.run / "last.pt"
    if ckpt.exists():
        state = torch.load(ckpt, map_location="cpu", weights_only=False)
        if state["plan"] != config["plan"] or state["train_sha256"] != train_sha:
            raise SystemExit("checkpoint was made with another training file or batch order")
        model.load_state_dict(state["model"], strict=False)
        opt.load_state_dict(state["opt"])
        sched.load_state_dict(state["sched"])
        torch.set_rng_state(state["torch_rng"])
        step = state["step"]
        log({"event": "resumed", "step": step, "total": total})
    else:
        if args.init:
            init = torch.load(args.init, map_location="cpu", weights_only=False)
            weights = init["model"] if "model" in init else init  # last.pt or epochN.pt
            if model.load_state_dict(weights, strict=False).unexpected_keys:
                raise SystemExit(f"{args.init} is not a checkpoint of this model")
        (args.run / "config.json").write_text(json.dumps(config, indent=2) + "\n", "utf-8")
        log({"event": "start", "total": total, "per_epoch": per_epoch, "items": len(train_enc),
             **({"init_sha256": config["init_sha256"]} if args.init else {})})  # fmt: skip

    def checkpoint() -> None:
        save_checkpoint(ckpt, {
            "model": trainable_state(model), "opt": opt.state_dict(),
            "sched": sched.state_dict(), "torch_rng": torch.get_rng_state(), "step": step,
            "plan": config["plan"], "train_sha256": train_sha,
        })  # fmt: skip

    budget = args.budget_min * 60
    window: list[tuple[float, float, float]] = []
    t_last = time.time()
    while step < total:
        if time.time() - t_start > budget:
            checkpoint()
            log({"event": "paused", "step": step, "total": total})
            return EXIT_PAUSED
        model.train()
        idx = plan[step]
        n_items = len(idx)
        n_span = max(1, sum(train_enc[i].span_start != NO_SPAN for i in idx))
        stance_total = span_total = 0.0
        for piece in micro_batches(idx, lengths, args.max_tokens):
            batch = collate([train_enc[i] for i in piece], tok.pad_token_id)
            if args.trap_weight != 1.0:
                batch["weights"] = torch.tensor([item_weight[i] for i in piece])
            logits, start, end = model(
                batch["input_ids"], batch["attention_mask"], batch["record_mask"]
            )
            stance_sum, span_sum = loss_sums(logits, start, end, batch)
            loss = stance_sum / n_items + args.span_weight * span_sum / n_span
            loss.backward()
            stance_total += stance_sum.item()
            span_total += span_sum.item()
        stance_loss, span_loss = stance_total / n_items, span_total / n_span
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        now = time.time()
        window.append((stance_loss, span_loss, now - t_last))
        t_last = now
        if step % 25 == 0:
            n = len(window)
            mean = [round(sum(w[k] for w in window) / n, 4) for k in range(3)]
            log({"step": step, "epoch": round(step / per_epoch, 3), "stance_loss": mean[0],
                 "span_loss": mean[1], "lr": sched.get_last_lr()[0],
                 "sec_per_step": mean[2]})  # fmt: skip
            window = []
        if step % args.ckpt_every == 0:
            checkpoint()
        if step % args.eval_every == 0 or step % per_epoch == 0 or step == total:
            t_eval = time.time()
            m = evaluate(model, dev_enc, dev_items, tok.pad_token_id,
                         args.run / "dev" / f"step{step:05d}.predictions.jsonl")  # fmt: skip
            log({"event": "dev", "step": step, **m, "eval_sec": round(time.time() - t_eval)})
            t_last = time.time()
        if step % per_epoch == 0 and step < total:
            torch.save(trainable_state(model), args.run / f"epoch{step // per_epoch}.pt")
    checkpoint()
    meta = {
        "arm": "classifier",
        "base_model": BASE_MODEL,
        "base_revision": BASE_REVISION,
        "train_sha256": train_sha,
        "features_version": features.VERSION,
        "max_len": args.max_len,
        "dropout": args.dropout,
        "policy": Policy().to_dict(),
        "training": config,
    }
    digest = export(model, tok, args.run / "final", meta)
    log({"event": "done", "step": step, "model_sha256": digest})
    return 0


if __name__ == "__main__":
    sys.exit(main())
