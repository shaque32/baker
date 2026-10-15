"""Speed bar for the small stance model: seconds per stance decision on case01, timed through the
product pipeline (GO_BAR.md, condition 4: at most 4.52 s per decision on Arsh's 24 GB Mac).

    python -m eval.stancemodel.time_case01 --model <exported model folder> \
        [--out eval/out/stancemodel/speed] [--threads N]

Builds case01 fresh as the eval does, runs the audit with the classifier as the stance labeler
(assumptions from the case's sheet, the product's retrieval, quote check, checks and rules), and
times every label call: building the input from the case database, the model, and cutting the
quote. Model loading is timed apart. Also reports what the run put in front of the expert
(eval.probe.time_case.surfacing), for reading next to the 14B's numbers; that is not a bar here.

Eval only: core/ does not import this. The case is SYNTHETIC; nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core import pipeline
from core.audit import invariants
from core.audit.checks._common import CaseData, person_party
from core.audit.context import build_context
from core.contracts import Assumption, EvidenceCandidate, GoldClaim, ModelRun, Stance, StanceLabel
from eval import run_pipeline as rp
from eval.probe import time_case
from eval.run_eval import load_jsonl
from eval.stancedata import gobar
from eval.stancemodel import features
from eval.stancemodel.encode import best_quote, encode
from eval.stancemodel.policy import Policy, decide

MODEL_NAME = "baker-stance-classifier"
RATIONALE = "Classifier label; the quote is the span the model marked in the record."
CLAIM_TEMPLATES = frozenset({"meaning", "role", "event"})  # their text points at "the claim"
WINDOW = 3  # messages either side of the record; the training excerpts hold at most six lines
_ZONE_NOTE = re.compile(r"\s*\(UTC[+-]\d\d:\d\d\)$")


class Parties:
    """Who an account is, as far as Baker's own checks know it: the persons an expert-confirmed
    device_owner stipulation or an expert-confirmed identity link ties its app and identifier to
    (core.audit.checks._common.person_party). Proposed and rejected ones never count, so nothing
    here merges an identity the expert has not confirmed. Read once, when the labeler is built."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.data = CaseData(conn)
        pids = {pid for _, _, pid, status in self.data.stipulations if status == "confirmed"}
        pids |= {pid for _, _, pid in self.data.links}
        self.keys = {pid: person_party(self.data, pid).keys for pid in sorted(pids)}

    def persons(self, account_id: str) -> list[str]:
        acc = self.data.accounts.get(account_id)
        if acc is None:
            return []
        return [pid for pid, keys in self.keys.items() if acc.key in keys]

    def account_of(self, record_id: str) -> str | None:
        """The account a context line's record came from: a message's sender, a call's caller."""
        if record_id.startswith("contact:"):
            return None
        sql = (
            "SELECT from_account_id FROM calls WHERE id = ?"
            if record_id.startswith("call:")
            else "SELECT sender_account_id FROM messages WHERE id = ?"
        )
        row = self.conn.execute(sql, (record_id,)).fetchone()
        return row[0] if row else None

    def sender(self, line: Any) -> str:
        """'<app> <id>[ <shown as>][ (owner)][ [<person ids>]]'. "(owner)" marks the phone's own
        account (accounts are kept per phone, so only the record's phone's own); a line with no
        account keeps Baker's text ("unknown sender", "contact list")."""
        aid = self.account_of(line.record_id)
        acc = self.data.accounts.get(aid) if aid else None
        if acc is None:
            return str(line.sender)
        out = f"{acc.app} {acc.identifier}"
        if line.shown_as:
            out += f" {line.shown_as}"
        if acc.is_owner:
            out += " (owner)"
        persons = self.persons(acc.id)
        if persons:
            out += f" [{', '.join(persons)}]"
        return out

    def device_of(self, record_id: str) -> str | None:
        """The phone a record was extracted from."""
        if record_id.startswith("call:"):
            sql = "SELECT device_id FROM calls WHERE id = ?"
        elif record_id.startswith("contact:"):
            sql = "SELECT device_id FROM contacts WHERE id = ?"
        elif record_id.startswith("att:"):
            sql = (
                "SELECT t.device_id FROM attachments a JOIN messages m ON m.id = a.message_id"
                " JOIN threads t ON t.id = m.thread_id WHERE a.id = ?"
            )
        else:
            sql = (
                "SELECT t.device_id FROM messages m JOIN threads t ON t.id = m.thread_id"
                " WHERE m.id = ?"
            )
        row = self.conn.execute(sql, (record_id,)).fetchone()
        return row[0] if row else None


def case_item(
    conn: sqlite3.Connection,
    assumption: Assumption,
    cand: EvidenceCandidate,
    window: int,
    parties: Parties | None = None,
) -> dict[str, Any]:
    """One (assumption, record in context) pair from the case database, as the model reads it.

    The assumption is Baker's own text. The lines are Baker's context lines (core.audit.context):
    sender as Parties.sender writes it, the phone's local time without its "(UTC-05:00)" note,
    the body as stored. The record's text is the text a quote is checked against
    (core.audit.invariants): a contact reads "Name +1...", a call "outgoing call from ... to ...
    at ..., 123s", an attachment its file name (after its parent message's own line when that
    message has a caption). device_id names the phone the record was extracted from. For the
    meaning, role and event templates, whose text points at "the claim", baker_claim carries the
    claim's text (Arsh's decision of 2026-10-14; the 14B prompt gets the same once its change is
    signed).
    The Baker-form training items (eval/train, eval/heldout) are written to match this exactly;
    tell the "Custom model for Baker" thread before changing it or WINDOW."""
    parties = parties or Parties(conn)
    text = invariants.record_text(conn, cand.record_id) or cand.text
    lines = build_context(conn, cand.record_id, window)
    rows = [
        {
            "sender": parties.sender(ln),
            "local_time": _ZONE_NOTE.sub("", ln.local_time),
            "text": ln.body,
        }
        for ln in lines
    ]
    targets = [i for i, ln in enumerate(lines) if ln.is_target]
    if targets:
        t = targets[0]
        if cand.record_id.startswith("att:") and (lines[t].body or "").strip():
            # A captioned attachment: the parent message reads as its own line, then the
            # attachment, marked, with the same sender and time. Caption-less: one line.
            rows.insert(t, dict(rows[t]))
            t += 1
        rows[t]["text"] = text
    else:
        rows, t = [{"sender": "unknown sender", "local_time": "time unknown", "text": text}], 0
    item: dict[str, Any] = {
        "probe_id": cand.record_id,
        "assumption": assumption.text,
        "target": rows[t],
        "context": rows[:t] + rows[t + 1 :],
        "target_index": t,
    }
    device = parties.device_of(cand.record_id)
    if device:
        item["device_id"] = device
    if getattr(assumption, "template_id", None) in CLAIM_TEMPLATES:
        row = conn.execute(
            "SELECT text FROM claims WHERE id = ?", (assumption.claim_id,)
        ).fetchone()
        if row:
            item["baker_claim"] = row[0]
    return item


class ClassifierLabeler:
    """core.contracts.StanceLabeler on an exported small stance model, with per-call timing."""

    def __init__(self, conn: sqlite3.Connection, model_dir: Path, window: int = WINDOW) -> None:
        from eval.stancemodel.model import load_exported

        t0 = time.perf_counter()
        self.model, self.tok, self.meta = load_exported(model_dir)
        self.load_seconds = time.perf_counter() - t0
        self.conn = conn
        self.window = window
        self.parties = Parties(conn)
        self.policy = Policy.from_dict(self.meta.get("policy"))
        self.seconds: list[float] = []
        self.labels: Counter[str] = Counter()
        run_id = f"mr:stance:{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}:{self.meta['model_sha256'][:12]}"
        params: dict[str, str | int | float | bool] = {
            "max_len": int(self.meta["max_len"]),
            "window": window,
            **{f"policy_{k}": float(v) for k, v in self.policy.to_dict().items()},
        }
        self.run = ModelRun(
            id=run_id,
            purpose="stance",
            model_name=MODEL_NAME,
            model_sha256=self.meta["model_sha256"],
            prompt_version=f"stancemodel features {features.VERSION}",
            params=params,
            seed=None,
            started_at_utc=rp._clock(),
        )
        self.model_runs = (self.run,)

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        from eval.stancemodel.model import score_items

        t0 = time.perf_counter()
        item = case_item(self.conn, assumption, candidate, self.window, self.parties)
        enc = encode(item, self.tok, int(self.meta["max_len"]))
        scores = score_items(self.model, [enc], self.tok.pad_token_id, batch_size=1)[0]
        stance = decide(scores["probs"], self.policy)
        quote = "" if stance == "irrelevant" else best_quote(enc, scores["start"], scores["end"])
        self.seconds.append(time.perf_counter() - t0)
        self.labels[stance] += 1
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=Stance(stance),
            quote=quote or "",
            rationale=RATIONALE,
            model_run_id=self.run.id,
        )


def run(model_dir: Path, out: Path, case: str = "case01") -> dict[str, Any]:
    spec = time_case.default_spec()
    conn = rp.build_case(case, out / f"{case}.db")
    try:
        labeler = ClassifierLabeler(conn, model_dir)
        comps = pipeline.real_components(
            conn, replace={"labeler": labeler}, filler=rp.spec_filler(spec, conn)
        )
        t0 = time.perf_counter()
        result = pipeline.run_audit(conn, comps, clock=rp._clock)
        wall = time.perf_counter() - t0
        gold = load_jsonl(Path("eval/gold") / case / "gold.jsonl", GoldClaim)
        surfaced = time_case.surfacing(conn, gold)
    finally:
        conn.close()
    secs = sorted(labeler.seconds)
    per_call = statistics.mean(secs) if secs else None
    return {
        "case": case,
        "machine": time_case.machine(),
        "model_dir": str(model_dir),
        "model_sha256": labeler.meta["model_sha256"],
        "policy": labeler.policy.to_dict(),
        "assumption_spec": str(spec),
        "model_load_seconds": round(labeler.load_seconds, 2),
        "stance_calls": len(secs),
        "mean_seconds_per_call": round(per_call, 4) if per_call is not None else None,
        "median_seconds_per_call": round(statistics.median(secs), 4) if secs else None,
        "p95_seconds_per_call": round(secs[int(0.95 * (len(secs) - 1))], 4) if secs else None,
        "max_seconds_per_call": round(secs[-1], 4) if secs else None,
        "audit_wall_seconds": round(wall, 1),
        "bar_seconds_per_call": round(gobar.MAX_SECONDS_PER_CALL, 2),
        "meets_speed_bar": per_call is not None and per_call <= gobar.MAX_SECONDS_PER_CALL,
        "labels": dict(labeler.labels),
        "verdicts": dict(Counter(d.verdict.value for d in result.decisions)),
        "dropped_labels": result.dropped_labels,
        "surfacing": {k: v for k, v in surfaced.items() if k != "per_claim"},
    }


def markdown(s: dict[str, Any]) -> str:
    m = s["machine"]
    sf = s["surfacing"]
    return "\n".join([
        f"# Small stance model speed on {s['case']}",
        "",
        f"Machine: {m.get('cpu')}, {m.get('ram_gb')} GB, {m.get('platform')}",
        f"Model: {s['model_dir']} (sha256 {s['model_sha256']}), policy {s['policy']}",
        "",
        "| stance calls | mean s/call | median | p95 | max | bar | meets bar | model load s "
        "| audit wall s |",
        "|---|---|---|---|---|---|---|---|---|",
        f"| {s['stance_calls']} | {s['mean_seconds_per_call']} | {s['median_seconds_per_call']} "
        f"| {s['p95_seconds_per_call']} | {s['max_seconds_per_call']} "
        f"| {s['bar_seconds_per_call']} | {s['meets_speed_bar']} | {s['model_load_seconds']} "
        f"| {s['audit_wall_seconds']} |",
        "",
        f"Labels: {s['labels']}. Verdicts: {s['verdicts']}. Dropped labels: "
        f"{s['dropped_labels']}.",
        f"Key evidence surfaced in the gold direction: {sf['key_evidence_recall']} "
        f"(retrieved {sf['key_evidence_retrieved']}); claims ready for the expert: "
        f"{sf['claims_ready_for_expert']}/{sf['claims_needing_key_evidence']}; supporting items "
        f"for the expert: {sf['supporting_items_for_expert']}; key evidence in the wrong "
        f"direction: {', '.join(sf['key_evidence_wrong_direction']) or 'none'}.",
        "",
    ])  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    import torch

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, required=True, help="exported model folder")
    ap.add_argument("--out", type=Path, default=Path("eval/out/stancemodel/speed"))
    ap.add_argument("--threads", type=int, default=0, help="torch CPU threads (0: torch default)")
    args = ap.parse_args(argv)
    if args.threads:
        torch.set_num_threads(args.threads)
    args.out.mkdir(parents=True, exist_ok=True)
    summary = run(args.model, args.out)
    summary["torch_threads"] = torch.get_num_threads()
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    md = markdown(summary)
    (args.out / "summary.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
