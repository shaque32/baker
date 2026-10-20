"""Check a reproducibility bundle offline (`baker verify-bundle`).

Nothing here touches a case or the network. The bundle's tables are loaded into a database in
memory, built from core/schema.sql, and checked in this order; any failure fails the bundle:

1. Files: every file matches the SHA-256 bundle.json lists, and nothing is added or missing.
2. Versions: the rules and contracts that decided the verdicts are this copy's; otherwise it
   names the Baker commit to verify with, since only those rules can reproduce them.
3. Tables: each row has exactly the schema's columns, and every reference resolves.
4. Audit log: the hash chain holds from the first entry, its last hash is the one bundle.json
   names, the last entry is this export, and every expert evidence decision in the log matches
   the stored review (and the other way round).
5. Inputs: each import entry in the log names the file hash stored for that source; with
   --inputs, files there are hashed and compared.
6. Labels: each evidence item's id still matches its content, its label is the model's answer
   as stored (tables/model_calls.jsonl), and its quote is found word for word in the record.
   Model calls are compared with the digests the audit log recorded for them (pipeline.claim's
   model_calls; cloud.received's raw_sha256 for a hosted model's answers).
7. Verdicts: the verdict rules, re-applied to the recorded labels, checks, stipulations and the
   expert decisions as they stood when each verdict was decided, give every verdict exactly
   (verdict, basis, reasons, coverage, citations), and the expert's confirmations and
   overrides in the log replay to the stored outcome.
8. Report: the report rendered from these tables is byte for byte the report in the bundle.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core import db, pipeline
from core.audit import quotes, rules, stance
from core.audit._llm_json import BadModelOutput, parse_json_object
from core.audit._local_model import RECEIVED_ACTION
from core.bundle import export
from core.contracts import (
    CONTRACTS_VERSION,
    EvidenceStatus,
    Stance,
    Stipulation,
    StipulationStatus,
    SupportedBasis,
    Verdict,
    canonical_json,
    evidence_id,
)
from core.db import apply_schema
from core.enrich.records import get_record
from core.ingest import forwarded
from core.llm import cloud
from core.report import html as report_html
from core.review import audit_log
from core.timeline.settings import Settings

PASS, FAIL, NOTE = "pass", "fail", "note"


@dataclass(frozen=True)
class Finding:
    level: str  # pass, fail or note
    check: str
    detail: str


class _Out:
    def __init__(self) -> None:
        self.items: list[Finding] = []

    def add(self, level: str, check: str, detail: str) -> None:
        self.items.append(Finding(level, check, detail))

    def failed(self, check: str | None = None) -> bool:
        return any(f.level == FAIL and (check is None or f.check == check) for f in self.items)


def failed(findings: list[Finding]) -> bool:
    return any(f.level == FAIL for f in findings)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def verify_bundle(path: Path, inputs_dir: Path | None = None) -> list[Finding]:
    out = _Out()
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as e:
        out.add(FAIL, "files", f"the bundle cannot be read as a zip ({e})")
        return out.items
    with zf:
        manifest = _files(zf, out)
        if manifest is None or out.failed():
            return out.items
        if not _versions(manifest, out):
            return out.items
        conn = _tables(zf, manifest, out)
        if conn is None:
            return out.items
        try:
            _audit_log(conn, manifest, out)
            _inputs(conn, manifest, out, inputs_dir)
            run = _run(conn, manifest, out)
            if run is not None:
                _labels(conn, run, out)
                _calls(conn, out)
                _verdicts(conn, run, out)
                _report(conn, zf, manifest, out)
        finally:
            conn.close()
    return out.items


# ---------------------------------------------------------------- 1. files


def _files(zf: zipfile.ZipFile, out: _Out) -> dict[str, Any] | None:
    names = zf.namelist()
    if len(names) != len(set(names)):
        out.add(FAIL, "files", "the zip holds the same file name twice")
        return None
    if export.MANIFEST not in names:
        out.add(FAIL, "files", f"no {export.MANIFEST}: this is not a Baker bundle")
        return None
    try:
        manifest = json.loads(zf.read(export.MANIFEST).decode("utf-8"))
        listed: dict[str, dict[str, Any]] = manifest["files"]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
        out.add(FAIL, "files", f"{export.MANIFEST} cannot be read ({e})")
        return None
    if manifest.get("format") != export.FORMAT:
        out.add(FAIL, "files", f"{export.MANIFEST} is not a {export.FORMAT}")
        return None
    major = str(manifest.get("bundle_version", "")).split(".")[0]
    if major != export.BUNDLE_VERSION.split(".")[0]:
        out.add(
            FAIL,
            "files",
            f"bundle format {manifest.get('bundle_version')} is not one this "
            f"Baker reads ({export.BUNDLE_VERSION})",
        )
        return None
    for name in names:
        if name != export.MANIFEST and name not in listed:
            out.add(FAIL, "files", f"{name} is in the zip but not listed in {export.MANIFEST}")
    for name, meta in sorted(listed.items()):
        if name not in names:
            out.add(FAIL, "files", f"{name} is listed but missing from the zip")
        elif hashlib.sha256(zf.read(name)).hexdigest() != meta.get("sha256"):
            out.add(FAIL, "files", f"{name} does not match its SHA-256 in {export.MANIFEST}")
    if not out.failed("files"):
        out.add(PASS, "files", f"{len(listed)} files match their SHA-256")
    return manifest


# ---------------------------------------------------------------- 2. versions


def _versions(manifest: dict[str, Any], out: _Out) -> bool:
    run = manifest.get("run") or {}
    commit = ((run.get("build") or {}).get("commit")) or "the one in bundle.json"
    ok = True
    if run.get("rule_version") != rules.RULE_VERSION:
        out.add(
            FAIL,
            "versions",
            f"the verdicts were decided under rules "
            f"{run.get('rule_version')}; this Baker has rules {rules.RULE_VERSION}. Verify "
            f"with Baker at commit {commit}.",
        )
        ok = False
    if run.get("contracts_version") != CONTRACTS_VERSION:
        out.add(
            FAIL,
            "versions",
            f"the case was made under contracts "
            f"{run.get('contracts_version')}; this Baker has {CONTRACTS_VERSION}. Verify "
            f"with Baker at commit {commit}.",
        )
        ok = False
    if ok:
        out.add(
            PASS,
            "versions",
            f"rules {rules.RULE_VERSION} and contracts {CONTRACTS_VERSION}, "
            "as recorded for the audit",
        )
    return ok


# ---------------------------------------------------------------- 3. tables


def _tables(zf: zipfile.ZipFile, manifest: dict[str, Any], out: _Out) -> sqlite3.Connection | None:
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    conn.execute("PRAGMA foreign_keys = OFF")  # rows load table by table; checked after
    try:
        for table, cols in export.schema_tables():
            name = f"{export.TABLES}{table}.jsonl"
            if name not in manifest["files"]:
                out.add(FAIL, "tables", f"{name} is missing")
                continue
            rows = []
            for n, line in enumerate(zf.read(name).decode("utf-8").splitlines(), 1):
                row = json.loads(line)
                if not isinstance(row, dict) or sorted(row) != sorted(cols):
                    out.add(FAIL, "tables", f"{name} line {n} does not have the schema's columns")
                    break
                rows.append(tuple(row[c] for c in cols))
            conn.executemany(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",  # noqa: S608
                rows,
            )
    except (ValueError, UnicodeDecodeError, db.DatabaseError) as e:
        out.add(FAIL, "tables", f"the tables cannot be loaded ({e})")
    if not out.failed("tables"):
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            t, rowid, parent, _ = broken[0]
            out.add(
                FAIL,
                "tables",
                f"{len(broken)} rows refer to missing rows (first: {t} row {rowid} -> {parent})",
            )
    if out.failed("tables"):
        conn.close()
        return None
    conn.execute("PRAGMA foreign_keys = ON")
    out.add(PASS, "tables", "every row has the schema's columns and every reference resolves")
    return conn


# ---------------------------------------------------------------- 4. audit log


def _log(conn: sqlite3.Connection) -> list[tuple[int, str, str, str, dict[str, Any]]]:
    return [
        (seq, at, actor, action, json.loads(p))
        for seq, at, actor, action, p in conn.execute(
            "SELECT seq, at_utc, actor, action, payload_json FROM audit_log ORDER BY seq"
        )
    ]


def _audit_log(conn: sqlite3.Connection, manifest: dict[str, Any], out: _Out) -> None:
    brk = audit_log.first_break(conn)
    if brk is not None:
        out.add(FAIL, "audit log", f"the hash chain is broken at entry {brk}")
        return
    head = conn.execute("SELECT seq, hash, actor, action FROM audit_log ORDER BY seq DESC LIMIT 1")
    seq, h, actor, action = head.fetchone() or (0, "", "", "")
    want = manifest.get("audit_log") or {}
    if h != want.get("last_hash") or seq != want.get("last_seq"):
        out.add(
            FAIL,
            "audit log",
            f"the log ends at entry {seq} ({h[:12]}...), not at the "
            f"entry bundle.json names ({want.get('last_seq')})",
        )
        return
    if action != export.EXPORT_ACTION or actor != manifest.get("created_by"):
        out.add(FAIL, "audit log", "the log's last entry is not this export")
        return
    problem = audit_log.decision_problem(conn)
    if problem is not None:
        out.add(FAIL, "audit log", problem[1])
        return
    out.add(PASS, "audit log", f"hash chain holds over {seq} entries; last hash {h}")


# ---------------------------------------------------------------- 5. inputs


def _inputs(
    conn: sqlite3.Connection, manifest: dict[str, Any], out: _Out, inputs_dir: Path | None
) -> None:
    stored = dict(conn.execute("SELECT id, sha256 FROM sources"))
    logged: dict[str, str] = {}
    for _seq, _at, _actor, action, p in _log(conn):
        if action == "import" and isinstance(p.get("source_id"), str):
            logged[p["source_id"]] = str(p.get("sha256"))
    listed = {i["source_id"]: i["sha256"] for i in manifest.get("inputs", [])}
    bad = False
    for sid, sha in sorted(stored.items()):
        if listed.get(sid) != sha:
            out.add(FAIL, "inputs", f"source {sid}: bundle.json lists another hash than the case")
            bad = True
        if sid in logged and logged[sid] != sha:
            out.add(
                FAIL,
                "inputs",
                f"source {sid}: its stored hash differs from the one logged when it was imported",
            )
            bad = True
    unlogged = sorted(set(stored) - set(logged))
    if not bad:
        out.add(PASS, "inputs", f"{len(stored)} input hashes match the case and the import log")
    if unlogged:
        out.add(
            NOTE,
            "inputs",
            "no import entry in the log for "
            + ", ".join(unlogged)
            + " (the government document's import is not logged); compare its hash with "
            "the original file",
        )
    if inputs_dir is None:
        out.add(NOTE, "inputs", "original files not checked (pass --inputs <folder>)")
        return
    found: dict[str, str] = {}
    for p in sorted(Path(inputs_dir).rglob("*")):
        if p.is_file():
            found[export._file_sha256(p)] = p.name
    for sid, sha in sorted(stored.items()):
        name = conn.execute("SELECT file_name FROM sources WHERE id = ?", (sid,)).fetchone()[0]
        if sha in found:
            out.add(PASS, "inputs", f"{name}: the original file matches its recorded SHA-256")
        elif any(n == name for n in found.values()):
            out.add(
                FAIL,
                "inputs",
                f"{name}: a file of that name is there, but its SHA-256 "
                "differs from the one recorded on import",
            )
        else:
            out.add(NOTE, "inputs", f"{name}: not among the files given")


# ---------------------------------------------------------------- the run


def _run(conn: sqlite3.Connection, manifest: dict[str, Any], out: _Out) -> dict[str, Any] | None:
    try:
        run, last = pipeline.view_run(conn), pipeline.last_run(conn)
    except Exception as e:  # noqa: BLE001 - an unreadable manifest is a failure, not a crash
        out.add(FAIL, "run", f"the audit run cannot be read ({e})")
        return None
    want = (manifest.get("run") or {}).get("run_id")
    if run is None or last is None or run.get("partial") or run["run_id"] != want:
        out.add(FAIL, "run", f"the bundle's latest completed audit is not {want}")
        return None
    if run.get("fake"):
        out.add(NOTE, "run", "a test run with stand-in components: nothing in it is a finding")
    return run


# ---------------------------------------------------------------- 6. labels


def _evidence_rows(conn: sqlite3.Connection, ids: list[str]) -> list[tuple]:
    return [
        r
        for eid in ids
        for r in conn.execute(
            "SELECT id, assumption_id, record_id, stance, quote, rationale, model_run_id"
            " FROM evidence_items WHERE id = ?",
            (eid,),
        )
    ]


def _answers(conn: sqlite3.Connection) -> dict[tuple[str, str], list[Any]]:
    """(model run, subject_json) -> the parsed stance answers stored with outcome ok."""
    out: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for run_id, subject, raw in conn.execute(
        "SELECT model_run_id, subject_json, raw_output FROM model_calls WHERE outcome = 'ok'"
    ):
        try:
            out[(run_id, subject)].append(stance.validate_stance_output(parse_json_object(raw)))
        except BadModelOutput:
            continue  # an ok call of another pass (claims, review), not a stance answer
    return out


def _stand_in(conn: sqlite3.Connection, model_run_id: str | None) -> bool:
    """A labeler that stored no model answers: the eval's stand-ins, or a test's. A real model
    run stores every call (core/pipeline.py flush_calls), and the claim entries' digests name
    them, so removing a real run's calls fails the model-call check instead."""
    if model_run_id is None:
        return True
    r = conn.execute("SELECT params_json FROM model_runs WHERE id = ?", (model_run_id,)).fetchone()
    if r is not None and json.loads(r[0]).get("stand_in"):
        return True
    calls = conn.execute(
        "SELECT 1 FROM model_calls WHERE model_run_id = ? LIMIT 1", (model_run_id,)
    )
    return calls.fetchone() is None


def _same_label(item: tuple, answer: Any) -> bool:
    _id, _a, _r, stance_, quote, rationale, _m = item
    if answer.quote != quote or not rationale.endswith(answer.rationale):
        return False
    if str(Stance(answer.stance).value) == stance_:
        return rationale == answer.rationale
    # Code may record a model's label as complicates, and says why in front of its rationale
    # (core/audit/stance.py subject_stance; core/ingest/forwarded.py).
    return stance_ == Stance.COMPLICATES.value and rationale.startswith(
        (stance.NOT_THE_MESSAGE, forwarded.STANCE_NOTE)
    )


def _labels(conn: sqlite3.Connection, run: dict[str, Any], out: _Out) -> None:
    ids = sorted({e for items in run["manifest"].values() for e in items["evidence"]})
    rows = _evidence_rows(conn, ids)
    if len(rows) != len(ids):
        out.add(FAIL, "labels", f"{len(ids) - len(rows)} evidence items the run names are missing")
        return
    answers = _answers(conn)
    same_quote_check = run["config"].get("quote_check") == quotes.VERSION
    stand_ins = 0
    bad = 0
    for item in rows:
        eid, aid, rid, stance_, quote, _rat, mrid = item
        if evidence_id(aid, rid, Stance(stance_), quote) != eid:
            out.add(FAIL, "labels", f"{eid}: its stance or quote was changed after it was stored")
            bad += 1
            continue
        if _stand_in(conn, mrid):
            stand_ins += 1
        elif not any(
            _same_label(item, a) for a in answers.get((mrid, canonical_json([aid, rid])), [])
        ):
            out.add(FAIL, "labels", f"{eid}: no stored model answer gives this label")
            bad += 1
            continue
        if same_quote_check:
            rec = get_record(conn, rid)
            if (
                rec is None
                or rec.text is None
                or not quotes.verify_quote(quote, rec.text)
                or not quotes.cites_record(quote, rec.text, rec.own)
            ):
                out.add(FAIL, "labels", f"{eid}: its quote is not found word for word in {rid}")
                bad += 1
    if not same_quote_check:
        out.add(
            NOTE,
            "labels",
            f"quotes not re-checked: the audit used quote check "
            f"{run['config'].get('quote_check')}, this Baker has {quotes.VERSION}",
        )
    if stand_ins:
        out.add(
            NOTE,
            "labels",
            f"{stand_ins} labels came from a labeler that stored no model answers (a test "
            "stand-in), so there is no answer to compare them with",
        )
    if not bad:
        out.add(
            PASS,
            "labels",
            f"{len(rows)} evidence items match their content and the answers as stored",
        )


def _calls(conn: sqlite3.Connection, out: _Out) -> None:
    calls = {
        cid: (outcome, prompt, raw)
        for cid, outcome, prompt, raw in conn.execute(
            "SELECT id, outcome, prompt, raw_output FROM model_calls"
        )
    }
    bound: set[str] = set()
    unbound_claims = 0
    bad = False
    log = _log(conn)
    for seq, _at, _actor, action, p in log:
        if action != pipeline.CLAIM_ACTION:
            continue
        digest = p.get("model_calls")
        if not isinstance(digest, dict):
            unbound_claims += 1
            continue
        try:
            got = pipeline.calls_digest([(cid, *calls[cid]) for cid in digest["ids"]])
        except KeyError as e:
            out.add(FAIL, "model calls", f"entry {seq} names model call {e} that is missing")
            bad = True
            continue
        if got["sha256"] != digest.get("sha256"):
            out.add(
                FAIL,
                "model calls",
                f"a prompt, answer or outcome recorded by entry {seq} was changed",
            )
            bad = True
        bound.update(digest["ids"])
    received = {p.get("raw_sha256") for _s, _a, _c, action, p in log if action == RECEIVED_ACTION}
    hosted = {
        cid
        for (cid,) in conn.execute(
            "SELECT mc.id FROM model_calls mc JOIN model_runs mr ON mr.id = mc.model_run_id"
            " WHERE mr.model_sha256 LIKE ? AND mc.raw_output != ''",
            (cloud.SHA_PREFIX + "%",),
        )
    }
    if received:
        for cid in sorted(hosted):
            if _sha(calls[cid][2]) not in received:
                out.add(
                    FAIL,
                    "model calls",
                    f"{cid}: this hosted model answer is not the one "
                    "the API returned (cloud.received)",
                )
                bad = True
    elif hosted:
        out.add(
            NOTE,
            "model calls",
            f"{len(hosted)} hosted model answers predate cloud.received "
            "entries, so only the evidence ids bind them",
        )
    if unbound_claims:
        out.add(
            NOTE,
            "model calls",
            f"{unbound_claims} claim entries predate model-call "
            "digests, so their calls are not bound to the log",
        )
    unlisted = len(calls) - len(bound)
    if not bad:
        out.add(
            PASS,
            "model calls",
            f"{len(bound)} model calls match the digests in the audit "
            f"log{f'; {unlisted} are not named by one' if unlisted else ''}",
        )


# ---------------------------------------------------------------- 7. verdicts


def _positions(log: list, run: dict[str, Any]) -> dict[str, int]:
    """Claim id -> the audit-log entry its verdict was decided at."""
    run_id = run["run_id"]
    if run["config"].get("mode") == "rules_only":
        seq = next(
            s
            for s, _a, _c, act, p in log
            if act == pipeline.RUN_ACTION and p.get("run_id") == run_id
        )
        return dict.fromkeys(run["manifest"], seq)
    return {
        p["claim_id"]: s
        for s, _a, _c, act, p in log
        if act == pipeline.CLAIM_ACTION and p.get("run_id") == run_id
    }


def _statuses_at(
    conn: sqlite3.Connection, log: list, position: int, ids: list[str]
) -> dict[str, EvidenceStatus]:
    """Each item's status as it stood when a verdict was decided at log entry `position`: the
    latest review recorded before it. An expert review counts from its evidence.decide entry;
    an AI review from the entry of the claim whose run wrote it."""
    decided = {p.get("review_id"): s for s, _a, _c, act, p in log if act == "evidence.decide"}
    claim_entries = {
        (p.get("run_id"), p.get("claim_id")): s
        for s, _a, _c, act, p in log
        if act == pipeline.CLAIM_ACTION
    }
    out: dict[str, EvidenceStatus] = {}
    for eid in ids:
        status = EvidenceStatus.OPEN
        for rid, kind, st, mrid in conn.execute(
            "SELECT r.id, r.reviewer_kind, r.status, r.model_run_id FROM evidence_reviews r"
            " WHERE r.evidence_id = ? ORDER BY r.seq",
            (eid,),
        ):
            if kind == "expert":
                at = decided.get(rid)
            else:
                prun = conn.execute(
                    "SELECT mr.pipeline_run_id, a.claim_id FROM model_runs mr, evidence_items e"
                    " JOIN assumptions a ON a.id = e.assumption_id WHERE mr.id = ? AND e.id = ?",
                    (mrid, eid),
                ).fetchone()
                at = claim_entries.get(tuple(prun)) if prun else None
            if at is not None and at <= position:
                status = EvidenceStatus(st)
        out[eid] = status
    return out


def _stipulations_at(
    conn: sqlite3.Connection, log: list, run: dict[str, Any], position: int
) -> list[Stipulation]:
    """The stipulations as the run read them: a full audit reads them once, when it starts;
    a verdict re-run when it decides."""
    full = run["config"].get("mode") != "rules_only"
    started = _dt(run["started_at_utc"])
    state: dict[str, tuple[str, str, str, str]] = {}  # id -> (status, actor, at, statement)
    for s, at, actor, act, p in log:
        if s >= position or (full and _dt(at) > started):
            continue
        if act == "stipulation.confirm":
            state[p["stipulation_id"]] = ("confirmed", actor, at, p.get("statement"))
        elif act == "stipulation.withdraw":
            old = state.get(p["stipulation_id"], ("", "", "", None))
            state[p["stipulation_id"]] = ("rejected", actor, at, old[3])
    out = []
    for st in pipeline.load_stipulations(conn):
        if st.id not in state:
            continue
        status, actor, at, statement = state[st.id]
        out.append(
            st.model_copy(
                update={
                    "status": StipulationStatus(status),
                    "decided_by": actor,
                    "decided_at_utc": _dt(at),
                    "statement": statement or st.statement,
                }
            )
        )
    return out


def _verdicts(conn: sqlite3.Connection, run: dict[str, Any], out: _Out) -> None:
    log = _log(conn)
    try:
        positions = _positions(log, run)
    except StopIteration:
        out.add(FAIL, "verdicts", f"the audit log has no entry closing run {run['run_id']}")
        return
    claims = {c.id: c for c in pipeline.load_claims(conn, include_removed=True)}
    stip_position = min(positions.values(), default=0)
    stipulations = _stipulations_at(conn, log, run, stip_position)
    actions = defaultdict(list)
    for _s, _a, actor, act, p in log:
        if act in ("verdict.override", "verdict.confirm"):
            actions[p.get("verdict_id")].append((actor, act, p))
    n = overridden = 0
    for claim_id, items in sorted(run["manifest"].items()):
        claim = claims.get(claim_id)
        if claim is None or claim_id not in positions:
            out.add(FAIL, "verdicts", f"{claim_id}: the claim or its log entry is missing")
            continue
        statuses = _statuses_at(conn, log, positions[claim_id], items["evidence"])
        evidence = [
            e.model_copy(update={"status": statuses[e.id]})
            for e in pipeline.load_evidence(conn, items["evidence"])
        ]
        decision = rules.decide_verdict(
            claim,
            pipeline.load_assumptions(conn, items["assumptions"]),
            evidence,
            pipeline.load_checks(conn, items["checks"]),
            stipulations,
            run["run_id"],
        )
        stored = pipeline.load_verdict(conn, claim_id, run["run_id"])
        if stored is None:
            out.add(FAIL, "verdicts", f"{claim_id}: no stored verdict for the run")
            continue
        problem = _compare(decision, stored, actions.get(stored.id, []))
        if problem:
            out.add(FAIL, "verdicts", f"{claim_id}: {problem}")
            continue
        n += 1
        overridden += any(a == "verdict.override" for _x, a, _p in actions.get(stored.id, []))
    if not out.failed("verdicts"):
        extra = f"; {overridden} then set by the expert, as logged" if overridden else ""
        out.add(PASS, "verdicts", f"the rules give all {n} verdicts exactly{extra}")


def _compare(decision: Any, stored: Any, actions: list[tuple[str, str, dict]]) -> str | None:
    for name in (
        "id",
        "rule_version",
        "reasons",
        "coverage",
        "cited_evidence_ids",
        "cited_check_ids",
        "cited_stipulation_ids",
    ):
        if getattr(decision, name) != getattr(stored, name):
            return f"the rules give other {name.replace('_', ' ')} than recorded"
    verdict, basis = decision.verdict, decision.supported_basis
    by: str | None = None
    note: str | None = None
    for actor, act, p in actions:
        if act == "verdict.override":
            verdict = Verdict(p["verdict"])
            basis = SupportedBasis.CONFIRMED if verdict == Verdict.SUPPORTED else None
            by, note = actor, p.get("note")
        else:
            if p.get("verdict") != verdict.value:
                return "a logged confirmation names another verdict than the one it confirmed"
            by, note = actor, None
    if (verdict, basis) != (stored.verdict, stored.supported_basis):
        return (
            f"the rules and the logged expert actions give {verdict.value}, but the stored "
            f"verdict is {stored.verdict.value}"
        )
    if (by, note) != (stored.confirmed_by, stored.override_note):
        return "the stored confirmation or override does not match the audit log"
    return None


# ---------------------------------------------------------------- 8. report


def _report(
    conn: sqlite3.Connection, zf: zipfile.ZipFile, manifest: dict[str, Any], out: _Out
) -> None:
    tl = manifest.get("timeline_settings") or {}
    settings = Settings(
        int(tl.get("tolerance_min", Settings.tolerance_min)),
        int(tl.get("gap_hours", Settings.gap_hours)),
    )
    rendered = report_html.render_report(conn, settings)
    if rendered.encode("utf-8") != zf.read(export.REPORT):
        out.add(FAIL, "report", "the report in the bundle is not the one these tables render")
        return
    out.add(PASS, "report", "the report is exactly the one these tables render")
