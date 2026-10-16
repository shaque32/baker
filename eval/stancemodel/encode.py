"""Token-level view of a rendered item: input ids, which tokens are the record's text, and the gold
quote as a token span. Also the way back: a token span to a quote that passes verify_quote.

Needs a Hugging Face fast tokenizer (offsets), not torch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.audit.quotes import find_quote, verify_quote
from eval.stancemodel.features import Rendered, drop_order, ordered_lines, render

LABELS = ("supports", "contradicts", "complicates", "irrelevant")
LABEL_ID = {s: i for i, s in enumerate(LABELS)}
NO_SPAN = -100  # irrelevant items carry no quote to learn


@dataclass(frozen=True)
class Encoded:
    probe_id: str
    input_ids: list[int]
    record_mask: list[bool]  # token covers part of the record's text
    offsets: list[tuple[int, int]]  # character offsets into the excerpt (0, 0 outside it)
    rendered: Rendered
    record_text: str
    label: int | None  # gold stance id, when the item has one
    span_start: int  # gold quote's first token, or NO_SPAN
    span_end: int  # gold quote's last token, or NO_SPAN


def _tokenize(tok: Any, r: Rendered) -> Any:
    return tok(r.assumption, r.excerpt, return_offsets_mapping=True, truncation=False)


def encode(item: dict[str, Any], tok: Any, max_len: int) -> Encoded:
    """Encode one item, dropping the context lines farthest from the record until it fits."""
    order = drop_order(item)
    lines, _ = ordered_lines(item)
    dropped = 0
    keep: set[int] | None = None
    r = render(item)
    enc = _tokenize(tok, r)
    while len(enc["input_ids"]) > max_len and dropped < len(order):
        dropped += 1
        keep = set(range(len(lines))) - set(order[:dropped])
        r = render(item, keep)
        enc = _tokenize(tok, r)
    if len(enc["input_ids"]) > max_len:
        enc = tok(
            r.assumption,
            r.excerpt,
            return_offsets_mapping=True,
            truncation="longest_first",
            max_length=max_len,
        )
    seq = enc.sequence_ids()
    offsets: list[tuple[int, int]] = []
    record_mask: list[bool] = []
    for sid, (a, b) in zip(seq, enc["offset_mapping"], strict=True):
        in_excerpt = sid == 1
        offsets.append((a, b) if in_excerpt else (0, 0))
        record_mask.append(in_excerpt and b > r.record_start and a < r.record_end)
    record_text = item["target"]["text"]
    label = LABEL_ID.get(item.get("gold_stance", ""))
    start = end = NO_SPAN
    quote = item.get("proposed_quote")
    if label is not None and LABELS[label] != "irrelevant" and quote:
        span = find_quote(quote, record_text)
        if span is not None:
            qs, qe = r.record_start + span[0], r.record_start + span[1]
            toks = [i for i, m in enumerate(record_mask) if m]
            first = [i for i in toks if offsets[i][1] > qs]
            last = [i for i in toks if offsets[i][0] < qe]
            if first and last and first[0] <= last[-1]:
                start, end = first[0], last[-1]
    return Encoded(
        probe_id=item["probe_id"],
        input_ids=list(enc["input_ids"]),
        record_mask=record_mask,
        offsets=offsets,
        rendered=r,
        record_text=record_text,
        label=label,
        span_start=start,
        span_end=end,
    )


def _word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def snap_to_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen [start, end) to whole words and trim outer whitespace."""
    start, end = max(0, start), min(len(text), end)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    while 0 < start < len(text) and _word(text[start - 1]) and _word(text[start]):
        start -= 1
    while 0 < end < len(text) and _word(text[end]) and _word(text[end - 1]):
        end += 1
    return start, end


def quote_from_span(e: Encoded, start_tok: int, end_tok: int) -> str | None:
    """The record text under a token span, widened to whole words; None unless verify_quote
    passes on it (core/audit/quotes.py)."""
    rs = e.rendered.record_start
    a = max(e.offsets[start_tok][0], rs) - rs
    b = min(e.offsets[end_tok][1], e.rendered.record_end) - rs
    if b <= a:
        return None
    a, b = snap_to_words(e.record_text, a, b)
    quote = e.record_text[a:b]
    return quote if quote and verify_quote(quote, e.record_text) else None


def best_quote(
    e: Encoded, start_scores: list[float], end_scores: list[float], max_tokens: int = 64
) -> str | None:
    """The highest-scoring record span (start <= end, at most max_tokens long) that passes
    verify_quote; falls back to the whole record text; None if even that does not pass."""
    toks = [i for i, m in enumerate(e.record_mask) if m]
    pairs = []
    for i in toks:
        for j in toks:
            if i <= j < i + max_tokens:
                pairs.append((start_scores[i] + end_scores[j], i, j))
    pairs.sort(reverse=True)
    for _, i, j in pairs[:20]:
        q = quote_from_span(e, i, j)
        if q is not None:
            return q
    return e.record_text if verify_quote(e.record_text, e.record_text) else None
