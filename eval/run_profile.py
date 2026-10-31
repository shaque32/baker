"""Where a recorded run spends its model time, and which calls it could have skipped.

Usage: python -m eval.run_profile --db <case.db> [--json <out.json>] [--max-gap 600]

Eval only, no model, read-only. Reads a finished run's case database and prints, for every
model job (model_runs.purpose):

  time       an estimate: wall time between consecutive model calls, from model_calls.at_utc,
             given to the later call. The database stores no per-call seconds, so a gap also
             holds the code that ran between two calls (retrieval, checks, writes); for a local
             model that is small next to a call. A gap longer than --max-gap seconds (a pause, a
             model load, a stopped run) is not counted, and the first call of each stretch has
             no gap.
  answers    for stance calls, the stance each answer gave, from raw_output
  checks     for stance calls, the code checks on the call's assumption: every check passed,
             one failed, one was inconclusive, or none ran; and for passed checks, whether the
             record was one the check itself cited (check_results.record_ids_json)
  reuse      prompt text a call shares from the start with the model call just before it,
             whatever that call's job (every job uses the one loaded model, so its cache holds
             the last call's prompt; this is what llama.cpp's prefix reuse can skip
             re-reading), and the text every prompt of a model run ends with (fixed
             instructions placed after the case data, which no call can reuse)

Calls answered from a stored output (an audit rerun reuses earlier answers, see
core/audit/_local_model.py) are counted apart and left out of every figure above: they took no
model time and read no prompt.

Shares of prompt text are counted in characters, not tokens; a token is a few characters, so
treat them as close, not exact. Only aggregate counts are printed: no claim, record or prompt
text, so it is safe on any synthetic case. Never run it on case02 (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.audit._local_model import REUSE_PARAM, _reuse_key
from eval.loss_report import _raw_stance, open_readonly

VERSION = "1.0.0"
MAX_GAP_S = 600.0
STANCES = ("supports", "contradicts", "complicates", "irrelevant", "unparsed")
CHECK_STATES = ("all passed", "a check failed", "inconclusive", "no check")
TIMES = "estimates: gaps between model_calls.at_utc, which include the code between calls"


@dataclass
class Job:
    purpose: str
    model_runs: int = 0
    calls: int = 0
    timed_calls: int = 0
    seconds: list[float] = field(default_factory=list)
    prompt_chars: int = 0
    shared_prefix_chars: int = 0  # with the model call just before it, any job
    fixed_tail_chars: int = 0  # text every prompt of a model run ends with, summed per call
    stored_answers: int = 0  # answered from a stored output, not by the model; not counted

    @property
    def total_s(self) -> float:
        return sum(self.seconds)

    def as_dict(self) -> dict[str, object]:
        mean = self.total_s / len(self.seconds) if self.seconds else None
        median = statistics.median(self.seconds) if self.seconds else None
        return {
            "purpose": self.purpose,
            "model_runs": self.model_runs,
            "calls": self.calls,
            "stored_answers": self.stored_answers,
            "timed_calls": self.timed_calls,
            "hours": round(self.total_s / 3600, 2),
            "mean_s": None if mean is None else round(mean, 1),
            "median_s": None if median is None else round(median, 1),
            "prompt_chars_mean": round(self.prompt_chars / self.calls) if self.calls else 0,
            "reused_prefix_share": _share(self.shared_prefix_chars, self.prompt_chars),
            "fixed_tail_share": _share(self.fixed_tail_chars, self.prompt_chars),
        }


@dataclass
class Profile:
    jobs: dict[str, Job] = field(default_factory=dict)
    untimed_gaps: int = 0  # gaps over --max-gap, not counted
    stance_answers: Counter[str] = field(default_factory=Counter)
    stance_checks: Counter[str] = field(default_factory=Counter)
    # (check state, stance) for every stance call
    stance_by_check: Counter[tuple[str, str]] = field(default_factory=Counter)
    passed_cited: int = 0  # stance calls on a record a passed check cited
    passed_cited_answers: Counter[str] = field(default_factory=Counter)
    stance_by_template: Counter[str] = field(default_factory=Counter)

    def total_s(self) -> float:
        return sum(j.total_s for j in self.jobs.values())

    def as_dict(self) -> dict[str, object]:
        stance = self.jobs.get("stance")
        n = stance.calls if stance else 0
        return {
            "run_profile": VERSION,
            "times": TIMES,
            "model_hours": round(self.total_s() / 3600, 2),
            "untimed_gaps": self.untimed_gaps,
            "jobs": [j.as_dict() for j in sorted(self.jobs.values(), key=lambda j: -j.total_s)],
            "stance_calls": n,
            "stance_answers": {s: self.stance_answers.get(s, 0) for s in STANCES},
            "stance_checks": {s: self.stance_checks.get(s, 0) for s in CHECK_STATES},
            "stance_by_check": {
                c: {s: self.stance_by_check.get((c, s), 0) for s in STANCES} for c in CHECK_STATES
            },
            "passed_check_cited_record": self.passed_cited,
            "passed_check_cited_record_answers": {
                s: self.passed_cited_answers.get(s, 0) for s in STANCES
            },
            "stance_by_template": dict(sorted(self.stance_by_template.items())),
        }


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def _at(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _prefix_len(a: str, b: str) -> int:
    return len(os.path.commonprefix([a, b]))


def _common_tail(prompts: list[str]) -> int:
    if not prompts:
        return 0
    return len(os.path.commonprefix([p[::-1] for p in prompts]))


def _check_states(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Each assumption's check state, and the records its passed checks cited."""
    outcomes: dict[str, list[str]] = defaultdict(list)
    cited: dict[str, set[str]] = defaultdict(set)
    rows = conn.execute("SELECT assumption_id, outcome, record_ids_json FROM check_results")
    for aid, outcome, records in rows:
        outcomes[aid].append(outcome)
        if outcome == "pass":
            cited[aid].update(json.loads(records or "[]"))
    states: dict[str, str] = {}
    for aid, seen in outcomes.items():
        if "fail" in seen:
            states[aid] = "a check failed"
        elif "inconclusive" in seen:
            states[aid] = "inconclusive"
        else:
            states[aid] = "all passed"
    return states, cited


def stored_answers(conn: sqlite3.Connection) -> set[str]:
    """Calls answered from a stored output, not by the model: their run reuses outputs, and an
    earlier call of the same job, model file, prompt file and settings, with the same prompt
    and an answer that was not an error, holds the same raw output (stored_output_lookup in
    core/audit/_local_model.py). The cloud labeler asks again after an unusable stored answer;
    a new answer identical to it would be counted here too."""
    runs = {
        run_id: (purpose, sha, prompt_sha or "", json.loads(params))
        for run_id, purpose, sha, prompt_sha, params in conn.execute(
            "SELECT id, purpose, model_sha256, prompt_sha256, params_json FROM model_runs"
        )
    }
    first: dict[tuple[str, ...], str] = {}
    out: set[str] = set()
    rows = conn.execute(
        "SELECT id, model_run_id, prompt, raw_output, outcome FROM model_calls ORDER BY at_utc, id"
    )
    for call_id, run_id, prompt, raw, outcome in rows:
        if run_id not in runs:
            continue
        purpose, sha, prompt_sha, params = runs[run_id]
        key = (purpose, sha, prompt_sha, _reuse_key(params), prompt)
        if key in first:
            if params.get(REUSE_PARAM) and raw == first[key]:
                out.add(call_id)
        elif outcome != "error":  # a failed call is never reused
            first[key] = raw
    return out


def build(conn: sqlite3.Connection, max_gap_s: float = MAX_GAP_S) -> Profile:
    prof = Profile()
    purpose_of: dict[str, str] = {}
    for run_id, purpose in conn.execute("SELECT id, purpose FROM model_runs"):
        purpose_of[run_id] = purpose
        prof.jobs.setdefault(purpose, Job(purpose)).model_runs += 1

    stored = stored_answers(conn)
    calls = conn.execute(
        "SELECT id, model_run_id, subject_json, prompt, raw_output, at_utc FROM model_calls"
        " ORDER BY at_utc, model_run_id, seq"
    ).fetchall()
    by_run: dict[str, list[str]] = defaultdict(list)
    for call_id, run_id, _, prompt, _, _ in calls:
        if call_id not in stored:
            by_run[run_id].append(prompt)
    tails = {run_id: _common_tail(prompts) for run_id, prompts in by_run.items()}
    for run_id in by_run:
        if len(by_run[run_id]) < 2:
            tails[run_id] = 0  # one prompt shares its whole text with itself

    template_of = dict(conn.execute("SELECT id, template_id FROM assumptions").fetchall())
    states, cited = _check_states(conn)
    prev_at: datetime | None = None
    prev_prompt: str | None = None  # one model serves every job, so one cache
    for call_id, run_id, subject, prompt, raw, at in calls:
        purpose = purpose_of.get(run_id, "unknown")
        job = prof.jobs.setdefault(purpose, Job(purpose))
        if call_id in stored:  # no model time, and the model's cache still holds prev_prompt
            job.stored_answers += 1
            prev_at = _at(at)
            continue
        job.calls += 1
        job.prompt_chars += len(prompt)
        job.fixed_tail_chars += tails[run_id]
        if prev_prompt is not None:
            job.shared_prefix_chars += _prefix_len(prev_prompt, prompt)
        prev_prompt = prompt
        now = _at(at)
        if prev_at is not None:
            gap = (now - prev_at).total_seconds()
            if 0 <= gap <= max_gap_s:
                job.seconds.append(gap)
                job.timed_calls += 1
            else:
                prof.untimed_gaps += 1
        prev_at = now
        if job.purpose != "stance":
            continue
        stance = _raw_stance(raw) or "unparsed"
        stance = stance if stance in STANCES else "unparsed"
        prof.stance_answers[stance] += 1
        ids = json.loads(subject)
        aid, record = (ids[0], ids[1]) if len(ids) >= 2 else (None, None)
        state = states.get(aid, "no check") if aid else "no check"
        prof.stance_checks[state] += 1
        prof.stance_by_check[(state, stance)] += 1
        prof.stance_by_template[template_of.get(aid, "unknown")] += 1
        if state == "all passed" and record in cited.get(aid, set()):
            prof.passed_cited += 1
            prof.passed_cited_answers[stance] += 1
    return prof


def _pct(part: int, whole: int) -> str:
    return f"{part} of {whole} ({100 * part / whole:.0f}%)" if whole else "0"


def render(prof: Profile) -> str:
    d = prof.as_dict()
    lines = [
        f"Run profile {VERSION}: an estimated {d['model_hours']} h of model time "
        f"({prof.untimed_gaps} gaps over the limit not counted). Times are {TIMES}.",
        "",
        "| job | calls | est. hours | est. mean s | est. median s | prompt chars | reused prefix"
        " | fixed tail |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for j in d["jobs"]:
        lines.append(
            f"| {j['purpose']} | {j['calls']} | {j['hours']} | {j['mean_s']} | {j['median_s']}"
            f" | {j['prompt_chars_mean']} | {j['reused_prefix_share']:.0%}"
            f" | {j['fixed_tail_share']:.0%} |"
        )
    stored = [f"{j['purpose']} {j['stored_answers']}" for j in d["jobs"] if j["stored_answers"]]
    if stored:
        lines += [
            "",
            "Answered from stored outputs, not by the model, and left out above: "
            + ", ".join(stored)
            + ".",
        ]
    n = d["stance_calls"]
    if n:
        a = d["stance_answers"]
        c = d["stance_checks"]
        lines += [
            "",
            f"Stance calls: {n}. Answered irrelevant: {_pct(a['irrelevant'], n)}. "
            f"On an assumption whose checks all passed: {_pct(c['all passed'], n)}, "
            f"of them on a record the check cited: {d['passed_check_cited_record']}.",
            "",
            "| checks on the assumption | calls | " + " | ".join(STANCES) + " |",
            "|---|---|" + "---|" * len(STANCES),
        ]
        for state in CHECK_STATES:
            row = d["stance_by_check"][state]
            lines.append(
                f"| {state} | {c[state]} | " + " | ".join(str(row[s]) for s in STANCES) + " |"
            )
        lines += ["", "| template | stance calls |", "|---|---|"]
        lines += [f"| {t} | {k} |" for t, k in d["stance_by_template"].items()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--json", type=Path)
    p.add_argument("--max-gap", type=float, default=MAX_GAP_S)
    args = p.parse_args(argv)
    if "case02" in str(args.db):
        print("case02 is the hidden held-out case; profile it only when a task names it")
        return 2
    conn = open_readonly(args.db)
    try:
        prof = build(conn, args.max_gap)
    finally:
        conn.close()
    print(render(prof))
    if args.json:
        args.json.write_text(json.dumps(prof.as_dict(), indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
