"""Overlap check: no generated item may copy or closely paraphrase Baker's test data.

    python -m eval.stancedata.contamination \
        --train eval/out/stancedata/train.jsonl \
        --heldout eval/out/stancedata/heldout_test.jsonl eval/out/stancedata/heldout_dev.jsonl

Two checks, both by script, nothing by eye:
1. Generated items (training and held-out) against the reference test data: the probe set
   P001-P097 and the older smoke items, case01 (messages, signed gold claims, assumption sheets,
   affidavit) and case02 (messages, draft key, affidavit). The generators never read any of it;
   this script is the only code in eval/stancedata, eval/train or eval/heldout that does.
2. Training items against the held-out set, so the exam shares no text with the lessons.

Every free text of an item (assumption, record, context lines, rationale) is compared with every
reference text after normalizing case, punctuation and spacing. A pair is flagged when:
- exact: the normalized texts are equal and have at least EXACT_MIN_TOKENS words;
- run: they share a contiguous run of at least RUN_MIN_TOKENS words that also covers at least
  RUN_MIN_SHARE of the shorter text (so a shared sentence frame like "the contact saved as" in two
  long assumptions does not count, but a copied message does);
- jaccard: their sets of word 3-grams overlap by at least JACCARD_MIN (light edits, reordering).
Equal texts shorter than EXACT_MIN_TOKENS ("ok thx", "where r u") are counted, not flagged:
independent chats share them by chance.

Exit status 1 if anything is flagged. The report lists every flag with both texts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from eval.stancedata.chat import read_jsonl

ROOT = Path(__file__).resolve().parents[2]

EXACT_MIN_TOKENS = 5
RUN_MIN_TOKENS = 6
RUN_MIN_SHARE = 0.6
JACCARD_MIN = 0.6
JACCARD_MIN_TOKENS = 5
# A 3-gram in more reference texts than this is a sentence frame; it still counts toward a pair's
# score but does not make two texts candidates on its own (keeps the run fast).
CANDIDATE_MAX_POSTINGS = 400

_WORD = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(unicodedata.normalize("NFKC", text).casefold()))


def grams(toks: tuple[str, ...], n: int = 3) -> set[tuple[str, ...]]:
    return {toks[i : i + n] for i in range(len(toks) - n + 1)}


def longest_run(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """Length of the longest contiguous run of words the two texts share."""
    best = 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


@dataclass(frozen=True)
class Text:
    source: str  # e.g. "probe P034 assumption", "case02 msg:item1:Chats!88", "train T000123 target"
    text: str


@dataclass
class Index:
    """Reference texts indexed by word 3-gram."""

    texts: list[Text] = field(default_factory=list)
    toks: list[tuple[str, ...]] = field(default_factory=list)
    grams: list[set[tuple[str, ...]]] = field(default_factory=list)
    postings: dict[tuple[str, ...], list[int]] = field(default_factory=lambda: defaultdict(list))
    exact: dict[tuple[str, ...], list[int]] = field(default_factory=lambda: defaultdict(list))

    def add(self, t: Text) -> None:
        toks = tokens(t.text)
        if not toks:
            return
        i = len(self.texts)
        self.texts.append(t)
        self.toks.append(toks)
        g = grams(toks)
        self.grams.append(g)
        for gram in g:
            self.postings[gram].append(i)
        self.exact[toks].append(i)


@dataclass(frozen=True)
class Flag:
    kind: str  # exact, run or jaccard
    score: float
    query: Text
    reference: Text

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "score": round(self.score, 3),
            "query": self.query.source,
            "query_text": self.query.text,
            "reference": self.reference.source,
            "reference_text": self.reference.text,
        }


@dataclass
class Result:
    name: str
    queries: int = 0
    references: int = 0
    flags: list[Flag] = field(default_factory=list)
    short_exact: int = 0  # equal texts under EXACT_MIN_TOKENS words: counted, not flagged


def compare(name: str, queries: Iterable[Text], index: Index) -> Result:
    res = Result(name=name, references=len(index.texts))
    seen: dict[tuple[str, ...], list[Flag]] = {}
    for q in queries:
        res.queries += 1
        qt = tokens(q.text)
        if not qt:
            continue
        if len(qt) < EXACT_MIN_TOKENS and qt in index.exact:
            res.short_exact += 1
        if qt in seen:  # same normalized text already checked: reuse its verdict
            res.flags += [Flag(f.kind, f.score, q, f.reference) for f in seen[qt]]
            continue
        found: list[Flag] = []
        if len(qt) >= EXACT_MIN_TOKENS:
            found += [Flag("exact", 1.0, q, index.texts[i]) for i in index.exact.get(qt, ())]
        exact_hits = set(index.exact.get(qt, ()))
        qg = grams(qt)
        candidates: set[int] = set()
        for gram in qg:
            posting = index.postings.get(gram)
            if posting and len(posting) <= CANDIDATE_MAX_POSTINGS:
                candidates.update(posting)
        for i in sorted(candidates - exact_hits):
            rt, rg = index.toks[i], index.grams[i]
            shorter = min(len(qt), len(rt))
            run = longest_run(qt, rt)
            if run >= RUN_MIN_TOKENS and run >= RUN_MIN_SHARE * shorter:
                found.append(Flag("run", run / shorter, q, index.texts[i]))
                continue
            if min(len(qt), len(rt)) >= JACCARD_MIN_TOKENS and qg and rg:
                jac = len(qg & rg) / len(qg | rg)
                if jac >= JACCARD_MIN:
                    found.append(Flag("jaccard", jac, q, index.texts[i]))
        seen[qt] = found
        res.flags += found
    return res


# ------------------------------------------------------------------------------- reference data


def _jsonl(path: Path) -> list[dict]:
    return read_jsonl(path) if path.exists() else []


def _probe_texts(path: Path, label: str) -> Iterator[Text]:
    for row in _jsonl(path):
        pid = row.get("probe_id") or row.get("id")
        if "target" in row:  # ProbeItem format
            yield Text(f"{label} {pid} assumption", row["assumption"])
            yield Text(f"{label} {pid} record", row["target"]["text"])
            for n, line in enumerate(row["context"]):
                yield Text(f"{label} {pid} context {n}", line["text"])
            yield Text(f"{label} {pid} rationale", row.get("rationale", ""))
        else:  # smoke format: context is one string of formatted lines
            for key in ("assumption", "record_text", "quote"):
                if row.get(key):
                    yield Text(f"{label} {pid} {key}", row[key])
            for n, line in enumerate(str(row.get("context", "")).splitlines()):
                yield Text(f"{label} {pid} context {n}", line.split(": ", 1)[-1])


def _gold_texts(path: Path, label: str) -> Iterator[Text]:
    for row in _jsonl(path):
        cid = row.get("claim_id")
        yield Text(f"{label} {cid} claim", row.get("text", ""))
        for n, a in enumerate(row.get("core_assumptions", [])):
            yield Text(f"{label} {cid} assumption {n}", a)
        yield Text(f"{label} {cid} rationale", row.get("rationale", ""))


def _assumption_sheet_texts(path: Path, label: str) -> Iterator[Text]:
    for row in _jsonl(path):
        cid = row.get("claim_id")
        params = row.get("params", {})
        for key in ("quoted_text", "text", "assumption"):
            if isinstance(params.get(key), str):
                yield Text(f"{label} {cid} {key}", params[key])
        for key in ("note", "assumption", "text"):
            if isinstance(row.get(key), str):
                yield Text(f"{label} {cid} {key}", row[key])


def _markdown_paragraphs(path: Path, label: str) -> Iterator[Text]:
    if not path.exists():
        return
    for n, para in enumerate(path.read_text(encoding="utf-8").split("\n\n")):
        for m, sentence in enumerate(re.split(r"(?<=[.!?])\s+", para.strip())):
            if sentence:
                yield Text(f"{label} paragraph {n}.{m}", sentence)


def _case_messages(case: str) -> Iterator[Text]:
    if case == "case01":
        from eval.synthetic import generate as gen
    else:
        from eval.synthetic import case02_generate as gen
    for rendered in gen.build():
        for msg in rendered.messages:
            yield Text(f"{case} {msg['id']}", msg["body"] or "")


def reference_texts(root: Path = ROOT) -> Iterator[Text]:
    """Every text of the probe set, case01 and case02 that a generated item must not copy."""
    yield from _probe_texts(root / "eval/gold/probe/probe.jsonl", "probe(signed)")
    yield from _probe_texts(root / "eval/probe_draft/probe_draft.jsonl", "probe(draft)")
    for smoke in sorted((root / "eval/probe").glob("smoke_*.jsonl")):
        yield from _probe_texts(smoke, f"smoke({smoke.stem})")
    yield from _gold_texts(root / "eval/gold/case01/gold.jsonl", "case01 gold")
    yield from _gold_texts(root / "eval/synthetic/case01/draft_gold.jsonl", "case01 draft key")
    for sheet in sorted((root / "eval").glob("**/case01_assumptions.jsonl")):
        yield from _assumption_sheet_texts(sheet, "case01 assumptions")
    yield from _assumption_sheet_texts(root / "eval/gold/case01/assumptions.jsonl", "case01 gold")
    yield from _markdown_paragraphs(root / "eval/gold/case01/affidavit.md", "case01 affidavit")
    yield from _markdown_paragraphs(
        root / "eval/synthetic/case01/affidavit_draft.md", "case01 affidavit draft"
    )
    yield from _case_messages("case01")
    yield from _gold_texts(root / "eval/synthetic/case02/draft_gold.jsonl", "case02 key")
    yield from _markdown_paragraphs(
        root / "eval/synthetic/case02/affidavit_draft.md", "case02 affidavit"
    )
    yield from _case_messages("case02")


def item_text_list(rows: Iterable[dict], label: str) -> Iterator[Text]:
    for row in rows:
        pid = row["probe_id"]
        yield Text(f"{label} {pid} assumption", row["assumption"])
        yield Text(f"{label} {pid} record", row["target"]["text"])
        yield Text(f"{label} {pid} rationale", row["rationale"])
        for n, line in enumerate(row["context"]):
            yield Text(f"{label} {pid} context {n}", line["text"])


def _index(texts: Iterable[Text]) -> Index:
    idx = Index()
    for t in texts:
        idx.add(t)
    return idx


def run(train: list[Path], heldout: list[Path], root: Path = ROOT) -> list[Result]:
    train_rows = [r for p in train for r in read_jsonl(p)]
    heldout_rows = [r for p in heldout for r in read_jsonl(p)]
    ref = _index(reference_texts(root))
    results = []
    if train_rows:
        results.append(compare("train vs test data", item_text_list(train_rows, "train"), ref))
    if heldout_rows:
        results.append(
            compare("held-out vs test data", item_text_list(heldout_rows, "heldout"), ref)
        )
    if train_rows and heldout_rows:
        held = _index(item_text_list(heldout_rows, "heldout"))
        results.append(compare("train vs held-out", item_text_list(train_rows, "train"), held))
    return results


def report(results: list[Result], limit: int = 200) -> str:
    out = ["# Overlap check", ""]
    out.append("| comparison | texts checked | reference texts | flagged | short equal texts |")
    out.append("|---|---|---|---|---|")
    for r in results:
        out.append(
            f"| {r.name} | {r.queries} | {r.references} | {len(r.flags)} | {r.short_exact} |"
        )
    for r in results:
        if not r.flags:
            continue
        out += ["", f"## {r.name}: {len(r.flags)} flagged", ""]
        for f in r.flags[:limit]:
            out.append(f"- {f.kind} {f.score:.2f}: {f.query.source} {f.query.text!r}")
            out.append(f"  matches {f.reference.source} {f.reference.text!r}")
        if len(r.flags) > limit:
            out.append(f"- ... {len(r.flags) - limit} more in the JSON report")
    passed = not any(r.flags for r in results)
    out += ["", "PASS: no overlap." if passed else "FAIL: overlap found."]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--train", type=Path, nargs="*", default=[])
    ap.add_argument("--heldout", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, default=Path("eval/out/stancedata/contamination"))
    args = ap.parse_args(argv)
    results = run(args.train, args.heldout)
    args.out.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "comparison": r.name,
            "queries": r.queries,
            "references": r.references,
            "short_exact": r.short_exact,
            "flags": [f.as_dict() for f in r.flags],
        }
        for r in results
    ]
    (args.out / "report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    md = report(results)
    (args.out / "report.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 1 if any(r.flags for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
