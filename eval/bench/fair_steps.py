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
4. The fills against the signed assumption sheet, with no labeler. 4a: a claim counts when its
   fills hold every signed core template as often as the sheet does. 4b: each signed core
   assumption also needs its own fill with the same value for every parameter the sheet states.

Measures 1 strict and 4 were added after Codex's reviews of PR #93 (2026-10-16 16:46Z and
17:00Z), after the opus arm ran and before the local arm; `--rescore` adds them to a finished
arm from its stored databases with no model call. Each result records the commit it ran at, and
`--compare LOCAL OPUS` applies the decision rule to two results. PREREGISTERED.md (with its
amendments) says how each measure enters the decision.

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
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
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
MIN_FRAGMENT_WORDS = 3  # a strict fragment states something: "PETROV" or "March 6" does not
_LIST_PARAMS = frozenset({"account_ids", "person_ids", "device_ids", "handles", "channels"})


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
    sharing any one word counts; `strict` counts it only when it has at least
    MIN_FRAGMENT_WORDS content words and at least MATCH_AT of them are in that gold claim, so
    neither unrelated fragments of a paragraph nor bare keywords can pool words."""
    by_para: dict[str, list[GoldClaim]] = {}
    for g in gold:
        by_para.setdefault(str(g.para_no), []).append(g)
    assigned: dict[str, list[Proposal]] = {g.claim_id: [] for g in gold}
    for p in proposals:
        pw = words(p.text)
        if strict and len(pw) < MIN_FRAGMENT_WORDS:
            continue
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


def _utc(value: Any) -> Any:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return value


def params_match(signed: dict[str, Any], filled: dict[str, Any]) -> bool:
    """Every parameter the signed row states has the same value in the fill: lists as sets, the
    window by its start and end, quoted text with case and whitespace folded. A parameter the
    sheet leaves empty is not compared."""
    for key, want in signed.items():
        if want in (None, "", []):
            continue
        got = filled.get(key)
        if key in _LIST_PARAMS:
            ok = set(want) == set(got or ())
        elif key == "window":
            ok = isinstance(got, dict) and all(
                _utc(want.get(k)) == _utc(got.get(k)) for k in ("start_utc", "end_utc")
            )
        elif key == "quoted_text":
            ok = isinstance(got, str) and " ".join(want.casefold().split()) == " ".join(
                got.casefold().split()
            )
        elif key == "duration_s":
            ok = got is not None and list(want) == list(got)
        else:  # expected_count, count_op
            ok = want == got
        if not ok:
            return False
    return True


def sheet_coverage(
    sheet: list[dict[str, Any]], fills: list[tuple[str, str, dict[str, Any]]]
) -> dict[str, Any]:
    """Measure 4. `sheet` is the signed sheet's rows, `fills` the (claim id, template id, params)
    of each core assumption the filler wrote. 4a: a claim is covered when its fills hold every
    signed core template at least as often as the sheet does. 4b: each signed core row also has
    its own fill of that template whose parameters match (first match taken, in sheet order).
    Extra fills are listed, not penalized (an extra core assumption can only hold a claim back)."""
    want: dict[str, list[dict[str, Any]]] = {}
    for r in sheet:
        if r.get("is_core"):
            want.setdefault(r["claim_id"], []).append(r)
    have: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for cid, tid, params in fills:
        have.setdefault(cid, []).append((tid, params))
    rows = []
    for cid in sorted(want):
        mine = have.get(cid, [])
        signed = Counter(r["template_id"] for r in want[cid])
        got = Counter(t for t, _ in mine)
        missing, extra = signed - got, got - signed
        free = list(range(len(mine)))
        wrong = []
        for r in want[cid]:
            hit = next(
                (i for i in free if mine[i][0] == r["template_id"]
                 and params_match(r.get("params", {}), mine[i][1])),
                None,
            )  # fmt: skip
            if hit is None:
                wrong.append(r["template_id"])
            else:
                free.remove(hit)
        rows.append(
            {
                "claim_id": cid,
                "covered": not missing,
                "params_covered": not wrong,
                "missing": sorted(missing.elements()),
                "params_missed": sorted(wrong),
                "extra": sorted(extra.elements()),
            }
        )
    return {
        "covered": sum(r["covered"] for r in rows),
        "params_covered": sum(r["params_covered"] for r in rows),
        "claims": len(rows),
        "rows": rows,
    }


def sheet_step(audit_db: Path) -> dict[str, Any]:
    path = rp.assumption_sheet(CASE)
    if path is None:
        raise SystemExit(f"no assumption sheet for {CASE}")
    sheet = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    conn = sqlite3.connect(audit_db)
    try:
        rows = conn.execute(
            "SELECT claim_id, template_id, params_json FROM assumptions WHERE is_core = 1"
        ).fetchall()
        people = rp.sheet_people(conn)
    finally:
        conn.close()
    return sheet_coverage(canonical_people(sheet, people),
                          [(c, t, json.loads(pj or "{}")) for c, t, pj in rows])  # fmt: skip


def canonical_people(sheet: list[dict[str, Any]], people: dict[str, str]) -> list[dict[str, Any]]:
    """The sheet names people by surname ('person:petrov'); the case and the filler use the
    stipulated owner's id. Map them as the eval's own sheet path does (run_pipeline.spec_filler),
    so a fill that names the right person is not counted wrong."""
    out = []
    for r in sheet:
        params = dict(r.get("params", {}))
        if params.get("person_ids"):
            params["person_ids"] = [people.get(p, p) for p in params["person_ids"]]
        out.append({**r, "params": params})
    return out


def run_model_sha(db: Path) -> str | None:
    """The model hash the case database recorded for its stance run."""
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT model_sha256 FROM model_runs WHERE purpose = 'stance'"
            " AND model_name NOT LIKE 'gold-direction%' ORDER BY started_at_utc LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def revision() -> dict[str, Any]:
    """The commit this code ran at, and whether tracked files had uncommitted changes."""
    git = shutil.which("git")
    if git is None:
        return {"commit": None, "dirty": None}

    def run(*args: str) -> str:
        done = subprocess.run([git, *args], capture_output=True, text=True, check=False)  # noqa: S603 - fixed arguments
        return done.stdout.strip() if done.returncode == 0 else ""

    commit = run("rev-parse", "HEAD") or None
    return {"commit": commit, "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


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
            f"- Fills against the signed sheet, templates (4a): {sh['covered']} of {sh['claims']}"
            f" claims hold every signed core template (missing: {'; '.join(short) or 'none'})"
        )
        if "params_covered" in sh:
            off = [f"{r['claim_id']} ({', '.join(r['params_missed'])})"
                   for r in sh["rows"] if r["params_missed"]]  # fmt: skip
            lines.append(
                f"- Fills against the signed sheet, with parameters (4b): {sh['params_covered']}"
                f" of {sh['claims']} (not matched: {'; '.join(off) or 'none'})"
            )
    rev = res.get("revision")
    if rev:
        lines.append(
            f"- Ran at {rev['commit']}" + (" with uncommitted changes" if rev["dirty"] else "")
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
    ap.add_argument("--arm", choices=("local", "opus"))
    ap.add_argument("--models", type=Path, default=Path("eval/probe/models.local.json"))
    ap.add_argument("--model-name", default=None, help="local arm: the entry to use (default: 14B)")
    ap.add_argument("--effort", default="medium", choices=EFFORTS, help="opus arm: API effort")
    ap.add_argument("--skip-claims", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--rescore", action="store_true", help="add measures 1 strict and 4 to a finished --out"
    )
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("LOCAL", "OPUS"),
                    help="apply the decision rule to two result files, no model call")  # fmt: skip
    args = ap.parse_args(argv)
    if args.compare is None and args.arm is None:
        ap.error("give --arm, or --compare LOCAL OPUS")
    out = args.out or Path("eval/out/fair_steps") / (args.arm or "")
    if args.compare:
        local, opus = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        print(compare(local, opus))
        return 0
    if args.rescore:
        return rescore(out)
    model = (
        local_model(args.models, args.model_name)
        if args.arm == "local"
        else cloud_model(args.effort)
    )
    res: dict[str, Any] = {
        "arm": args.arm, "model": model.name, "model_sha256": model.sha256, "revision": revision()
    }  # fmt: skip
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


MARGIN = 2  # claims of 20 a step needs to move toward Opus (PREREGISTERED.md)
STEPS = (
    ("Claim proposal", ("1 split-aware", "1 strict")),
    ("Assumption filling", ("3 fills, lenient", "4b fills vs sheet")),
)


def decision_counts(res: dict[str, Any]) -> dict[str, int | None]:
    """The decision measures of one arm, as claims of 20."""
    c, f, sh = res.get("claims") or {}, res.get("fills_only") or {}, res.get("sheet") or {}
    n = sh.get("claims") or 20
    acc = f.get("verdict_accuracy")
    return {
        "1 split-aware": len(c["split_found"]) if "split_found" in c else None,
        "1 strict": len(c["split_found_strict"]) if "split_found_strict" in c else None,
        "3 fills, lenient": round(acc * n) if acc is not None else None,
        "4b fills vs sheet": sh.get("params_covered"),
    }


def compare(local: dict[str, Any], opus: dict[str, Any]) -> str:
    """The decision rule (PREREGISTERED.md, amendments 1 and 2) on two arms' results: a step
    moves toward Opus only if Opus wins by MARGIN on both of its measures with 0 false
    supported. Anything that makes the two runs not comparable is listed first; an INVALID
    arm, a dirty tree or two different recorded commits leave every step undecided. A missing
    commit (an arm that predates the field) is listed and does not block, as the plan says."""
    checks, blocking = [], []
    for name, r in (("local", local), ("opus", opus)):
        if r.get("arm") != name:
            blocking.append(f"the {name} file is the {r.get('arm')!r} arm: give LOCAL then OPUS")
        if not r.get("model_sha256"):
            (blocking if name == "local" else checks).append(f"{name} arm recorded no model hash")
        if r.get("invalid"):
            blocking.append(f"{name} arm is INVALID: {r['invalid']}")
        rev = r.get("revision") or {}
        if not rev.get("commit"):
            checks.append(f"{name} arm recorded no commit")
        elif rev.get("dirty"):
            blocking.append(f"{name} arm ran with uncommitted changes")
    a, b = (r.get("revision", {}).get("commit") for r in (local, opus))
    if a and b and a != b:
        blocking.append(f"the arms ran at different commits: list `git diff --stat {b} {a}`")
    checks = blocking + checks
    lo, op = decision_counts(local), decision_counts(opus)
    false_sup = {
        name: sum((r.get(k) or {}).get("n_false_supported", 0) for k in ("audit", "fills_only"))
        for name, r in (("local", local), ("opus", opus))
    }
    lines = ["# 14B vs Opus, the decision", ""]
    lines += [f"- CHECK: {c}" for c in checks] or ["- Both arms recorded a clean commit."]
    lines += [f"- Models: 14B {local.get('model')} ({local.get('model_sha256')}), "
              f"Opus {opus.get('model')} ({opus.get('model_sha256')})"]  # fmt: skip
    lines += ["", "| measure | 14B | Opus |", "|---|---|---|"]
    lines += [f"| {k} | {lo[k]} | {op[k]} |" for k in lo]
    lines += [f"| false supported (2 and 3) | {false_sup['local']} | {false_sup['opus']} |", ""]
    for step, keys in STEPS:
        known = all(lo[k] is not None and op[k] is not None for k in keys)
        wins = known and all(op[k] - lo[k] >= MARGIN for k in keys)  # type: ignore[operator]
        clean = false_sup["local"] == 0 and false_sup["opus"] == 0
        verdict = (
            "not decided: runs not comparable" if blocking
            else "not decided: a measure is missing" if not known
            else "moves toward Opus (a person reads the matched rows first)" if wins and clean
            else "stays local"
        )  # fmt: skip
        lines.append(f"- {step}: {verdict}")
    return "\n".join(lines) + "\n"


def rescore(out: Path) -> int:
    """Measures 1 strict and 4 for an arm that ran before they existed, from its stored
    databases. Writes result.rescored.json and summary.rescored.md beside the originals, with
    the commit the rescoring ran at."""
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    if res.get("claims"):
        res["claims"].update(strict_split(out / "claims" / f"{CASE}.db"))
    res["sheet"] = sheet_step(out / "audit" / f"{CASE}.db")
    res.setdefault("model_sha256", run_model_sha(out / "audit" / f"{CASE}.db"))
    res["rescored_at"] = revision()
    (out / "result.rescored.json").write_text(json.dumps(res, indent=2, default=str) + "\n",
                                              encoding="utf-8")  # fmt: skip
    md = summary(res)
    (out / "summary.rescored.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
