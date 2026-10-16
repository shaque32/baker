"""The 14B and Opus on the same test: claim splitting and assumption filling (case01, no sheet).

EVAL ONLY, synthetic case01. Arsh chose "Test after fixes" on the card "Run a fair test of Opus
vs the local model for claim splitting and assumption filling?" (thread "Cloud-first Opus with
offline fallback", 2026-10-15; taken 2026-10-16 after he said to approve what we believe is
correct). Both arms run this file at the same commit, which carries the quote-check and
affidavit-font fixes (#76):

  local  the local model (an entry of eval/probe/models.local.json), on the Mac
  opus   claude-opus-5-5 through core.llm.cloud, the eval's own client (eval/bench/cloud_steps)

Three measures, each through the product's own code:
1. Claim proposal on the case01 affidavit (core/claims/propose.py), scored two ways: the
   committed matcher (eval/probe/claim_recall.py, one proposal per gold claim) and split_match
   below, which credits a gold claim split into several proposals, as the claims prompt asks.
2. The full audit without the assumption sheet: the model fills the assumptions
   (core/audit/assumption_filler.py) and labels stance, then the simulated expert decides.
3. Assumption filling alone: measure 2's fills, replayed from its database with no model call,
   with the merge gate's gold-direction stand-in as the labeler. It shows how far the fills
   alone can take the verdicts, whatever the labeler. It is lenient: that stand-in labels every
   retrieved record the gold way and the simulated expert accepts a key record on any of the
   claim's assumptions, so a vague or wrong fill that retrieves a key record still scores.
4. The fills against the signed assumption sheet, with no labeler: a claim counts when its
   fills hold every signed core template as often as the sheet does. A vague fill cannot pass;
   parameters (windows, counts) are not compared.

Measures 1 (strict) and 4 were added after Codex's review of PR #93 (2026-10-16 16:46Z), after
the opus arm ran and before the local arm; `--rescore` adds them to a finished arm from its
stored databases with no model call. PREREGISTERED.md says how they enter the decision.

The plan and decision rule were written down before any call (PREREGISTERED.md beside the
results). Opus at medium effort is not deterministic and each arm runs once, so a one-claim
difference is noise.

Usage (from the repo root):
  python -m eval.bench.fair_steps --arm local [--models eval/probe/models.local.json]
  env -u ANTHROPIC_BASE_URL BAKER_ANTHROPIC_API_KEY="$BAKER_BENCH_API_KEY" \\
      python -m eval.bench.fair_steps --arm opus [--effort medium]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.contracts import GoldClaim
from core.llm.cloud import EFFORTS
from core.llm.runtime import ModelOutput
from eval import run_pipeline as rp
from eval.probe.claim_recall import MATCH_AT, recall_for, words
from eval.run_eval import load_jsonl, score

CASE = "case01"
_DIGITS = re.compile(r"\d+")


# 1. Claim proposal ------------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    id: str
    para_no: str
    text: str


def split_match(
    gold: list[GoldClaim], proposals: list[Proposal], strict: bool = False
) -> list[dict[str, Any]]:
    """One row per gold claim. Each proposal counts toward the one gold claim of its paragraph
    that holds the largest share of the proposal's content words (ties: the lower claim id),
    so a proposal never counts twice. A gold claim is found when its proposals together hold at
    least MATCH_AT of its content words and every number in it. As preregistered, a proposal
    sharing any one word counts; `strict` counts it only when at least MATCH_AT of its own
    words are in that gold claim, so unrelated fragments of a paragraph cannot pool words."""
    by_para: dict[str, list[GoldClaim]] = {}
    for g in gold:
        by_para.setdefault(str(g.para_no), []).append(g)
    assigned: dict[str, list[Proposal]] = {g.claim_id: [] for g in gold}
    for p in proposals:
        pw = words(p.text)
        best: tuple[float, str] | None = None
        for g in sorted(by_para.get(p.para_no, []), key=lambda g: g.claim_id):
            share = len(pw & words(g.text)) / len(pw) if pw else 0.0
            if (share >= MATCH_AT if strict else share > 0) and (best is None or share > best[0]):
                best = (share, g.claim_id)
        if best is not None:
            assigned[best[1]].append(p)
    rows = []
    for g in gold:
        mine = assigned[g.claim_id]
        held = set().union(*(words(p.text) for p in mine)) if mine else set()
        gw = words(g.text)
        cover = len(gw & held) / len(gw) if gw else 0.0
        nums = set(_DIGITS.findall(g.text)) <= set(_DIGITS.findall(" ".join(p.text for p in mine)))
        rows.append(
            {
                "claim_id": g.claim_id,
                "found": cover >= MATCH_AT and nums,
                "cover": round(cover, 2),
                "numbers_kept": nums,
                "proposals": [p.id for p in mine],
            }
        )
    return rows


def proposals_in(db: Path) -> list[Proposal]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT c.id, p.label, c.text FROM claims c"
            " JOIN govdoc_paragraphs p ON p.id = c.paragraph_id ORDER BY c.id"
        ).fetchall()
    finally:
        conn.close()
    return [Proposal(id=r[0], para_no=str(r[1]), text=r[2]) for r in rows]


def strict_split(db: Path) -> dict[str, Any]:
    gold = load_jsonl(rp.gold_path(CASE), GoldClaim)
    rows = split_match(gold, proposals_in(db), strict=True)
    return {
        "split_recall_strict": round(sum(r["found"] for r in rows) / len(gold), 3),
        "split_found_strict": [r["claim_id"] for r in rows if r["found"]],
        "split_rows_strict": rows,
    }


def claims_step(model: Any, out: Path) -> dict[str, Any]:
    gold = load_jsonl(rp.gold_path(CASE), GoldClaim)
    res = recall_for(model, CASE, out)
    split = split_match(gold, proposals_in(out / f"{CASE}.db"))
    found = sum(r["found"] for r in split)
    return {
        "proposed": res["proposed"],
        "dropped": res["dropped"],
        "committed_recall": res["recall"],
        "committed_found": [r["claim_id"] for r in res["rows"] if r["matched"]],
        "split_recall": round(found / len(gold), 3),
        "split_found": [r["claim_id"] for r in split if r["found"]],
        "split_rows": split,
        **strict_split(out / f"{CASE}.db"),
        "wall_seconds": res["wall_seconds"],
        "model_calls": res["model_calls"],
    }


# 2 and 3. The audit without the sheet -----------------------------------------------------


class ReplayModel:
    """Answers each prompt with the raw output a run in another case database gave it, so a
    second audit gets the same fills with no model call. A prompt it never saw is an error."""

    def __init__(self, db: Path, purpose: str) -> None:
        conn = sqlite3.connect(db)
        try:
            run = conn.execute(
                "SELECT model_name, model_sha256, params_json FROM model_runs WHERE purpose = ?"
                " ORDER BY started_at_utc LIMIT 1",
                (purpose,),
            ).fetchone()
            calls = conn.execute(
                "SELECT mc.prompt, mc.raw_output FROM model_calls mc"
                " JOIN model_runs mr ON mr.id = mc.model_run_id"
                " WHERE mr.purpose = ? AND mc.outcome != 'error' ORDER BY mc.at_utc, mc.id",
                (purpose,),
            ).fetchall()
        finally:
            conn.close()
        if run is None:
            raise LookupError(f"{db}: no {purpose} run to replay")
        self.name = f"replay of {run[0]}"
        self.sha256 = run[1]
        self.params = None
        self.where = "local"
        self._answers: dict[str, str] = {}
        for prompt, raw in calls:
            self._answers.setdefault(prompt, raw)

    def generate_json(self, prompt: str, schema: Any, params: Any = None) -> ModelOutput:
        if prompt not in self._answers:
            raise LookupError("replay: a prompt the first audit never sent")
        raw = self._answers[prompt]
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        return ModelOutput(raw_text=raw, parsed=parsed, error=None)


@contextmanager
def gold_direction_labeler(gold: list[GoldClaim]) -> Iterator[None]:
    """The merge gate's stand-in labels every record the way the gold verdict points; no AI
    reviewer. The filler is untouched."""
    from eval.pipeline_fakes import FakeReviewer
    from eval.simulated_expert import GoldDirectionLabeler, GoldKey

    orig = rp.pipeline.real_components

    def patched(conn, replace=None, filler=None, **kw):  # noqa: ANN001, ANN003, ANN202
        replace = dict(replace or {})
        replace["labeler"] = GoldDirectionLabeler(conn, GoldKey(gold))
        replace["reviewer"] = FakeReviewer(False)
        comps = orig(conn, replace=replace, filler=filler, **kw)
        comps.reviewable = lambda item: False
        comps.model_runs = (*comps.model_runs, *GoldDirectionLabeler.model_runs)
        return comps

    rp.pipeline.real_components = patched
    try:
        yield
    finally:
        rp.pipeline.real_components = orig


def audit_result(gold: list[GoldClaim], preds: list[Any], out: Path) -> dict[str, Any]:
    s = score(gold, preds)
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    return {
        "verdict_accuracy": round(s.verdict_accuracy, 3),
        "n_false_supported": s.n_false_supported,
        "confusion": s.confusion,
        "dropped_labels": run.get("dropped_labels"),
        "per_claim": {p.claim_id: str(getattr(p.verdict, "value", p.verdict)) for p in preds},
    }


def audit_step(model: Any, out: Path) -> dict[str, Any]:
    gold = load_jsonl(rp.gold_path(CASE), GoldClaim)
    start = time.perf_counter()
    preds = rp.run_once(CASE, "real", "accept", out, None, "simulated", labeler_model=model,
                        filler_model=model)  # fmt: skip
    res = audit_result(gold, preds, out)
    res["wall_seconds"] = round(time.perf_counter() - start, 1)
    return res


def fills_only_step(audit_out: Path, out: Path) -> dict[str, Any]:
    gold = load_jsonl(rp.gold_path(CASE), GoldClaim)
    replay = ReplayModel(audit_out / f"{CASE}.db", "assumptions")
    with gold_direction_labeler(gold):
        preds = rp.run_once(CASE, "real", "accept", out, None, "simulated", filler_model=replay)
    return audit_result(gold, preds, out)


def sheet_coverage(sheet: list[dict[str, Any]], fills: list[tuple[str, str]]) -> dict[str, Any]:
    """Measure 4. `sheet` is the signed sheet's rows, `fills` the (claim id, template id) of each
    core assumption the filler wrote. A claim is covered when its fills hold every signed core
    template at least as often as the sheet does; extra fills are listed, not penalized (an
    extra core assumption can only hold a claim back)."""
    want: dict[str, Counter[str]] = {}
    for r in sheet:
        if r.get("is_core"):
            want.setdefault(r["claim_id"], Counter())[r["template_id"]] += 1
    have: dict[str, Counter[str]] = {}
    for cid, tid in fills:
        have.setdefault(cid, Counter())[tid] += 1
    rows = []
    for cid in sorted(want):
        got = have.get(cid, Counter())
        missing, extra = want[cid] - got, got - want[cid]
        rows.append(
            {
                "claim_id": cid,
                "covered": not missing,
                "missing": sorted(missing.elements()),
                "extra": sorted(extra.elements()),
            }
        )
    return {"covered": sum(r["covered"] for r in rows), "claims": len(rows), "rows": rows}


def sheet_step(audit_db: Path) -> dict[str, Any]:
    path = rp.assumption_sheet(CASE)
    if path is None:
        raise SystemExit(f"no assumption sheet for {CASE}")
    sheet = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    conn = sqlite3.connect(audit_db)
    try:
        fills = conn.execute("SELECT claim_id, template_id FROM assumptions WHERE is_core = 1")
        return sheet_coverage(sheet, [(c, t) for c, t in fills.fetchall()])
    finally:
        conn.close()


# The arms ---------------------------------------------------------------------------------


def pick_entry(entries: list[dict[str, Any]], name: str | None) -> dict[str, Any]:
    """The models-file entry the local arm uses: the one named, else the only one, else the one
    whose name says 14B. eval/probe/mac_v12.sh probes the same entry."""
    if name:
        pick = [e for e in entries if e["name"] == name]
    elif len(entries) == 1:
        pick = entries
    else:
        pick = [e for e in entries if "14b" in e["name"].lower()]
    if len(pick) != 1:
        names = ", ".join(e["name"] for e in entries)
        raise SystemExit(f"name one model with --model-name or MODEL_NAME (have: {names})")
    return pick[0]


def local_model(models: Path, name: str | None) -> Any:
    from core.audit._local_model import LazyModel, ModelConfig
    from core.llm.runtime import sha256_file

    entry = pick_entry(json.loads(models.read_text(encoding="utf-8")), name)
    path = Path(entry["path"]).expanduser()
    sha = entry.get("sha256") or sha256_file(path)
    return LazyModel(ModelConfig(name=entry["name"], path=path, sha256=sha, n_ctx=8192))


class Retried:
    """The cloud model under the product's retry policy (core/audit/_local_model.py SentLog:
    MAX_RETRIES more sends of a retryable failure, backing off). A sticky failure left after
    that (no network, a rejected key, the API down) pauses the product's audit; here it makes
    the run invalid, since a label dropped that way is not the model's answer, and every later
    call fails at once without a send. A refusal or a cut-off answer is the model's own failure
    and is dropped and counted, as in the product."""

    def __init__(self, model: Any, retries: int | None = None, sleep: Any = time.sleep) -> None:
        from core.llm.cloud import MAX_RETRIES

        self._m, self._sleep = model, sleep
        self._retries = MAX_RETRIES if retries is None else retries
        self.name, self.sha256 = model.name, model.sha256
        self.params, self.where = model.params, model.where
        self.failure: str | None = None

    def generate_json(self, prompt: str, schema: Any, params: Any = None) -> Any:
        from core.llm.cloud import CloudError

        if self.failure is not None:
            raise CloudError(f"not sent: an earlier call failed ({self.failure})", sticky=True)
        for attempt in range(1, self._retries + 2):
            try:
                return self._m.generate_json(prompt, schema, params)
            except CloudError as e:
                if e.retryable and attempt <= self._retries:
                    self._sleep(min(2.0**attempt, 30.0))
                    continue
                if e.sticky:
                    self.failure = e.reason[:300]
                raise
        raise AssertionError("unreachable")  # pragma: no cover

    def usage(self) -> dict[str, Any]:
        return self._m.usage()


def cloud_model(effort: str) -> Any:
    from core.llm import cloud
    from eval.bench.claude_bench import check_case
    from eval.bench.cloud_steps import Metered

    check_case(CASE)
    cfg = cloud.load_config()
    return Retried(Metered(cloud.ClaudeModel(cloud.CloudConfig(
        api_key=cfg.api_key, model=cloud.DEFAULT_MODEL, effort=effort))))  # fmt: skip


def summary(res: dict[str, Any]) -> str:
    c, a, f = res.get("claims"), res.get("audit"), res.get("fills_only")
    lines = [f"# 14B vs Opus, {res['arm']} arm ({res['model']})", ""]
    if res.get("invalid"):
        lines += [f"**INVALID, do not score: {res['invalid']}. Run it again.**", ""]
    if c:
        missed = [r["claim_id"] for r in c["split_rows"] if not r["found"]]
        lines.append(
            f"- Claim proposal: {c['proposed']} proposals; committed matcher "
            f"{c['committed_recall']:.0%}, split-aware {c['split_recall']:.0%} "
            f"(missed: {', '.join(missed) or 'none'}); {c['wall_seconds']} s"
        )
        if "split_recall_strict" in c:
            lost = [r["claim_id"] for r in c["split_rows_strict"] if not r["found"]]
            lines.append(
                f"- Claim proposal, strict split-aware (each fragment must match): "
                f"{c['split_recall_strict']:.0%} (missed: {', '.join(lost) or 'none'})"
            )
    for label, r in (("Full audit, no sheet", a), ("Fills only, lenient labeler", f)):
        if r:
            lines.append(
                f"- {label}: accuracy {r['verdict_accuracy']:.0%}, false supported "
                f"{r['n_false_supported']}, dropped labels {r['dropped_labels']}"
                + (f", {r['wall_seconds']} s" if "wall_seconds" in r else "")
            )
    sh = res.get("sheet")
    if sh:
        short = [f"{r['claim_id']} ({', '.join(r['missing'])})" for r in sh["rows"] if r["missing"]]
        lines.append(
            f"- Fills against the signed sheet: {sh['covered']} of {sh['claims']} claims hold every"
            f" signed core template (missing: {'; '.join(short) or 'none'})"
        )
    if a and f:
        lines += ["", "| claim | full audit | fills only |", "|---|---|---|"]
        lines += [f"| {k} | {a['per_claim'].get(k)} | {f['per_claim'].get(k)} |"
                  for k in sorted(a["per_claim"])]  # fmt: skip
    if res.get("usage"):
        lines += ["", f"Usage: {json.dumps(res['usage'])}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", choices=("local", "opus"), required=True)
    ap.add_argument("--models", type=Path, default=Path("eval/probe/models.local.json"))
    ap.add_argument("--model-name", default=None, help="local arm: the entry to use (default: 14B)")
    ap.add_argument("--effort", default="medium", choices=EFFORTS, help="opus arm: API effort")
    ap.add_argument("--skip-claims", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--rescore", action="store_true", help="add measures 1 strict and 4 to a finished --out"
    )
    args = ap.parse_args(argv)
    out = args.out or Path("eval/out/fair_steps") / args.arm
    if args.rescore:
        return rescore(out)
    model = (
        local_model(args.models, args.model_name)
        if args.arm == "local"
        else cloud_model(args.effort)
    )
    res: dict[str, Any] = {"arm": args.arm, "model": model.name}
    if args.arm == "opus":
        res["effort"] = args.effort
    out.mkdir(parents=True, exist_ok=True)
    if not args.skip_claims:
        print("1/3 claim proposal", file=sys.stderr, flush=True)
        res["claims"] = claims_step(model, out / "claims")
    print("2/3 the audit without the sheet (fills and labels)", file=sys.stderr, flush=True)
    res["audit"] = audit_step(model, out / "audit")
    print("3/3 the same fills with a perfect labeler (no model call)", file=sys.stderr, flush=True)
    res["fills_only"] = fills_only_step(out / "audit", out / "fills_only")
    res["sheet"] = sheet_step(out / "audit" / f"{CASE}.db")
    if hasattr(model, "usage"):
        res["usage"] = model.usage()
    if getattr(model, "failure", None):
        res["invalid"] = f"a cloud call failed after its retries ({model.failure})"
    (out / "result.json").write_text(json.dumps(res, indent=2, default=str) + "\n",
                                     encoding="utf-8")  # fmt: skip
    md = summary(res)
    (out / "summary.md").write_text(md, encoding="utf-8")
    print(md)
    return 1 if res.get("invalid") else 0


def rescore(out: Path) -> int:
    """Measures 1 strict and 4 for an arm that ran before they existed, from its stored
    databases. Writes result.rescored.json and summary.rescored.md beside the originals."""
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    if res.get("claims"):
        res["claims"].update(strict_split(out / "claims" / f"{CASE}.db"))
    res["sheet"] = sheet_step(out / "audit" / f"{CASE}.db")
    (out / "result.rescored.json").write_text(json.dumps(res, indent=2, default=str) + "\n",
                                              encoding="utf-8")  # fmt: skip
    md = summary(res)
    (out / "summary.rescored.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
