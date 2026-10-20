"""Check a reproducibility bundle offline (`baker verify-bundle`).

Nothing here touches a case or the network. The bundle's tables are loaded into a database in
memory, built from core/schema.sql, and checked in this order; any failure fails the bundle:

1. Files: every file matches the SHA-256 bundle.json lists, and the files listed are exactly a
   bundle's: nothing added or missing.
2. Versions: the rules and contracts that decided the verdicts are this copy's; otherwise it
   names the Baker commit to verify with, since only those rules can reproduce them.
3. Tables: each row has exactly the schema's columns, and every reference resolves.
4. Audit log: the hash chain holds from the first entry and every payload reads, its last hash
   is the one bundle.json names, and every expert evidence decision in the log matches the
   stored review (and the other way round). Nothing after this runs on a log that failed.
5. bundle.json: what it says that follows from the tables (run, models, inputs, contents, the
   timeline settings the log records, log head) is recomputed and must match; METHOD.md must
   be the note it gives.
6. Inputs: each import entry in the log names the file hash stored for that source; with
   --inputs, files there are hashed and compared.
7. Run and rows: the run's row is the one its pipeline.run entry recorded (run_sha256); the
   assumptions, check results, evidence items and AI reviews behind each verdict, the records
   they cite and the model runs they name are the ones its claim's audit-log entry recorded
   (pipeline.claim's rows_sha256).
8. Labels: each evidence item's id still matches its content and it cites its record's source;
   its label is the model's answer as stored (tables/model_calls.jsonl), exactly or as the
   pipeline rewrites it, and its quote is found word for word in the record. Each AI review
   naming a stored reviewer answer says what that answer said; each expert review is on the
   item, by the expert, at the time its evidence.decide entry names; each audited claim is the
   one its entry recorded (claim_sha256) or what logged claim.status changes made of it.
9. Model calls: compared with the digests the audit log recorded for them (pipeline.claim's
   model_calls; cloud.received's raw_sha256 for the hosted answers those digests name).
10. Stipulations and identity links: each is what the logged actions left.
11. Verdicts: the verdict rules, re-applied to the recorded labels, checks, stipulations and the
   expert decisions as they stood when each verdict was decided, give every verdict exactly
   (verdict, basis, reasons, coverage, citations) at the logged time, and the expert's
   confirmations and overrides in the log replay to the stored outcome.
12. Report: the report rendered from these tables is byte for byte the report in the bundle.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core import db, encryption, pipeline
from core.audit import quotes, rules, stance
from core.audit import review as review_mod
from core.audit._llm_json import BadModelOutput, parse_json_object
from core.audit._local_model import RECEIVED_ACTION
from core.bundle import export, sealed
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
    review_id,
)
from core.db import apply_schema
from core.enrich.records import get_record
from core.identity import links
from core.ingest import forwarded
from core.llm import cloud
from core.report import html as report_html
from core.review import audit_log

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


def outcome(findings: list[Finding]) -> tuple[int, str]:
    """(exit code, one line): 0 only when every check ran and passed; 2 when nothing failed but
    something could not be checked (each NOTE says what and why); 1 when anything failed."""
    fails = sum(f.level == FAIL for f in findings)
    gaps = sum(f.level == NOTE for f in findings)
    if fails:
        return 1, f"bundle FAILED: {fails} problems (and {gaps} things not verified)"
    if gaps:
        return 2, (
            f"bundle partly verified: nothing failed, but {gaps} things were not verified (the "
            "NOT VERIFIED lines say what and why)"
        )
    return 0, "bundle verified: every check ran and passed"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def verify_bundle(
    path: Path, inputs_dir: Path | None = None, passphrase: str | None = None
) -> list[Finding]:
    """Every check's findings. An encrypted bundle (core/bundle/sealed.py) needs `passphrase`."""
    out = _Out()
    try:
        data = Path(path).read_bytes()
        if sealed.is_sealed(data):
            if not passphrase:
                out.add(FAIL, "files", "the bundle is encrypted; give its passphrase")
                return out.items
            data = sealed.open_sealed(data, passphrase)
            out.add(PASS, "files", "the encrypted bundle opened with its passphrase, unaltered")
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile, encryption.EncryptionError, encryption.WrongSecret) as e:
        out.add(FAIL, "files", f"the bundle cannot be read ({e})")
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
            # Every later check reads the log, so nothing runs on a log that failed.
            if not _audit_log(conn, manifest, out):
                return out.items
            run = _run(conn, manifest, out)
            if run is None:
                return out.items
            _manifest(conn, zf, manifest, run, out)
            _inputs(conn, out, inputs_dir)
            _rows(conn, run, out)
            _labels(conn, run, out)
            _ai_reviews(conn, out)
            _expert_reviews(conn, out)
            _claims(conn, run, out)
            _calls(conn, out)
            _stipulations(conn, out)
            _identity(conn, out)
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
        if not isinstance(listed, dict) or not all(
            isinstance(m, dict) and isinstance(m.get("sha256"), str) for m in listed.values()
        ):
            raise TypeError("its files list is not a map of names to SHA-256 hashes")
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
    expected = {export.METHOD, export.REPORT} | {
        f"{export.TABLES}{t}.jsonl" for t, _cols in export.schema_tables()
    }
    for name in sorted(expected - set(listed)):
        out.add(FAIL, "files", f"{name} is not listed in {export.MANIFEST}")
    for name in sorted(set(listed) - expected):
        out.add(FAIL, "files", f"{name} is listed but is not part of a Baker bundle")
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
    except (ValueError, UnicodeDecodeError, *db.DatabaseError) as e:
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
    """The audit log's entries; read only after _audit_log passed (every payload parses)."""
    return [
        (seq, at, actor, action, json.loads(p))
        for seq, at, actor, action, p in conn.execute(
            "SELECT seq, at_utc, actor, action, payload_json FROM audit_log ORDER BY seq"
        )
    ]


def _audit_log(conn: sqlite3.Connection, manifest: dict[str, Any], out: _Out) -> bool:
    brk = audit_log.first_break(conn)
    if brk is not None:
        out.add(FAIL, "audit log", f"the hash chain is broken at entry {brk}")
        return False
    for seq, payload in conn.execute("SELECT seq, payload_json FROM audit_log ORDER BY seq"):
        try:
            if not isinstance(json.loads(payload), dict):
                raise ValueError("not a JSON object")
        except ValueError as e:
            out.add(FAIL, "audit log", f"entry {seq}'s payload cannot be read ({e})")
            return False
    head = conn.execute("SELECT seq, hash, actor, action FROM audit_log ORDER BY seq DESC LIMIT 1")
    seq, h, _actor, _action = head.fetchone() or (0, "", "", "")
    want = manifest.get("audit_log") or {}
    if not isinstance(want, dict) or h != want.get("last_hash") or seq != want.get("last_seq"):
        out.add(
            FAIL,
            "audit log",
            f"the log ends at entry {seq} ({h[:12]}...), not at the entry bundle.json names",
        )
        return False
    problem = audit_log.decision_problem(conn)
    if problem is not None:
        out.add(FAIL, "audit log", problem[1])
        return False
    out.add(PASS, "audit log", f"hash chain holds over {seq} entries; last hash {h}")
    return True


# ---------------------------------------------------------------- bundle.json and METHOD.md


def _manifest(
    conn: sqlite3.Connection,
    zf: zipfile.ZipFile,
    manifest: dict[str, Any],
    run: dict[str, Any],
    out: _Out,
) -> None:
    """Everything bundle.json says that follows from the tables (contents, run, inputs, models,
    audit-log head) is recomputed and must match exactly; METHOD.md must be the note
    bundle.json gives. The export's time and exporter are as the exporter wrote them: the
    case's own log records the export (bundle.export) with the bundle's SHA-256."""
    facts = export.derived(conn, run)
    listed_inputs = [
        {k: v for k, v in i.items() if k != "case_copy_matches_at_export"}
        for i in manifest.get("inputs") or []
        if isinstance(i, dict)
    ]
    bad = [
        key
        for key, want in facts.items()
        if (listed_inputs if key == "inputs" else manifest.get(key)) != want
    ]
    for key in bad:
        out.add(FAIL, "bundle.json", f"its {key} are not what the tables give")
    try:
        note = export.method_note(manifest)
    except (KeyError, TypeError, AttributeError) as e:
        out.add(FAIL, "bundle.json", f"it cannot be read as a method note's source ({e})")
        return
    if note.encode("utf-8") != zf.read(export.METHOD):
        out.add(FAIL, "bundle.json", f"{export.METHOD} is not the note bundle.json gives")
        bad.append(export.METHOD)
    if not bad:
        out.add(
            PASS,
            "bundle.json",
            f"its run, models, inputs, contents and log head match the tables, and "
            f"{export.METHOD} is the note they give",
        )


# ---------------------------------------------------------------- 5. inputs


def _inputs(conn: sqlite3.Connection, out: _Out, inputs_dir: Path | None) -> None:
    stored = dict(conn.execute("SELECT id, sha256 FROM sources"))
    logged: dict[str, str] = {}
    for _seq, _at, _actor, action, p in _log(conn):
        if action == "import" and isinstance(p.get("source_id"), str):
            logged[p["source_id"]] = str(p.get("sha256"))
    bad = False
    for sid, sha in sorted(stored.items()):
        if sid in logged and logged[sid] != sha:
            out.add(
                FAIL,
                "inputs",
                f"source {sid}: its stored hash differs from the one logged when it was imported",
            )
            bad = True
    unlogged = sorted(set(stored) - set(logged))
    if not bad:
        out.add(PASS, "inputs", f"{len(stored)} input hashes match the import log")
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
    if not Path(inputs_dir).is_dir():
        out.add(FAIL, "inputs", f"{inputs_dir} is not a folder, so no original file was checked")
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
    if (
        run is None
        or last is None
        or run.get("partial")
        or run["run_id"] != want
        or pipeline.latest_attempt(conn) is not None
    ):
        out.add(FAIL, "run", f"the bundle's latest completed audit is not {want}")
        return None
    if run.get("fake"):
        out.add(NOTE, "run", "a test run with stand-in components: nothing in it is a finding")
    _run_rows(conn, run, out)
    return run


def _run_rows(conn: sqlite3.Connection, run: dict[str, Any], out: _Out) -> None:
    """The run's pipeline_runs row (start, versions, configuration with build, cloud decision
    and quote check) is the one its pipeline.run entry recorded (run_sha256), completed at the
    time the entry names; and so is the row of the audit a verdict re-run took its evidence
    from."""
    entries = {
        p.get("run_id"): p for _s, _a, _c, act, p in _log(conn) if act == pipeline.RUN_ACTION
    }
    unbound = 0
    for run_id in dict.fromkeys((run["run_id"], run.get("evidence_from_run", run["run_id"]))):
        entry = entries.get(run_id) or {}
        want = entry.get("run_sha256")
        if not isinstance(want, str):
            unbound += 1
            continue
        row = conn.execute(
            "SELECT status, finished_at_utc, note FROM pipeline_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if (
            pipeline.run_digest(conn, run_id) != want
            or row is None
            or row[0] != "completed"
            or row[1] != entry.get("finished_at_utc")
            or row[2] is not None
        ):
            out.add(
                FAIL,
                "run",
                f"{run_id}: its versions, settings or times are not the ones its audit-log "
                "entry recorded",
            )
    if unbound:
        out.add(
            NOTE,
            "run",
            f"{unbound} audit runs predate run digests, so their versions and settings are "
            "not bound to the log",
        )
    elif not out.failed("run"):
        out.add(PASS, "run", "the audit's versions and settings are the ones its log recorded")


# ---------------------------------------------------------------- 6. labels


def _rows(conn: sqlite3.Connection, run: dict[str, Any], out: _Out) -> None:
    """The rows each verdict rests on (assumptions, check results, evidence items with their
    source and rationale, AI reviews) are the ones its claim's audit-log entry recorded a
    digest of (core/pipeline.py rows_digest)."""
    changed, unbound = export.changed_rows(conn, run)
    missing = sorted(set(run["manifest"]) - set(export.claim_entries(conn, run)))
    for claim_id in changed:
        out.add(
            FAIL,
            "rows",
            f"{claim_id}: an assumption, check result, evidence item or AI review was "
            "changed after the claim's audit-log entry recorded it",
        )
    for claim_id in missing:
        out.add(FAIL, "rows", f"{claim_id}: no audit-log entry records the claim's rows")
    if unbound:
        out.add(
            NOTE,
            "rows",
            f"{unbound} claim entries predate row digests, so their assumptions, checks, "
            "evidence and AI reviews are not bound to the log",
        )
    if not changed and not missing:
        out.add(
            PASS,
            "rows",
            f"the rows behind {len(run['manifest']) - unbound} verdicts are the ones their "
            "audit-log entries recorded, with the records they cite and the model runs they name",
        )
    covered = {
        str(r["id"])
        for claim_id, entry in export.claim_entries(conn, run).items()
        if isinstance(entry.get("rows_sha256"), str)
        for r in pipeline.claim_rows(conn, entry["manifest"], claim_id, export.entry_calls(entry))[
            "model_runs"
        ]
    }
    other = [mid for (mid,) in conn.execute("SELECT id FROM model_runs ORDER BY rowid")]
    other = [mid for mid in other if mid not in covered]
    if other:
        out.add(
            NOTE,
            "rows",
            f"{len(other)} model runs bundle.json lists are named by no audited row (e.g. an "
            f"earlier audit's, or one whose answers were all reused), so their model, prompt "
            f"and settings are not bound to the log: {', '.join(other[:5])}"
            + (" ..." if len(other) > 5 else ""),
        )


def _evidence_rows(conn: sqlite3.Connection, ids: list[str]) -> list[tuple]:
    return [
        r
        for eid in ids
        for r in conn.execute(
            "SELECT id, assumption_id, record_id, stance, quote, rationale, model_run_id,"
            " source_id, locator FROM evidence_items WHERE id = ?",
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


def _stand_in(conn: sqlite3.Connection, model_run_id: str | None, test_run: bool) -> bool:
    """A labeler that stored no model answers: the eval's stand-ins, or a test's. A real model
    run stores every call (core/pipeline.py flush_calls), and the claim entries' digests name
    them, so removing a real run's calls fails the model-call check instead. An item naming no
    model run counts as a stand-in's only in a test run."""
    if model_run_id is None:
        return test_run
    r = conn.execute("SELECT params_json FROM model_runs WHERE id = ?", (model_run_id,)).fetchone()
    if r is not None and json.loads(r[0]).get("stand_in"):
        return True
    calls = conn.execute(
        "SELECT 1 FROM model_calls WHERE model_run_id = ? LIMIT 1", (model_run_id,)
    )
    return calls.fetchone() is None


def _same_label(item: tuple, answer: Any) -> bool:
    """The item is the model's answer exactly, or exactly as the pipeline rewrites one it
    records as complicates (core/pipeline.py _Run._label): a "contradicts" on a record that is
    not the message the assumption is about (core/audit/stance.py subject_stance), or a
    "supports" or "contradicts" on forwarded words (core/ingest/forwarded.py)."""
    stance_, quote, rationale = item[3], item[4], item[5]
    if answer.quote != quote:
        return False
    model = Stance(answer.stance)
    if model.value == stance_:
        return rationale == answer.rationale
    if stance_ != Stance.COMPLICATES.value or model not in (Stance.SUPPORTS, Stance.CONTRADICTS):
        return False
    return rationale in (
        f"{forwarded.STANCE_NOTE}{model.value}. {answer.rationale}",
        *((stance.NOT_THE_MESSAGE + answer.rationale,) if model is Stance.CONTRADICTS else ()),
    )


def _labels(conn: sqlite3.Connection, run: dict[str, Any], out: _Out) -> None:
    ids = sorted({e for items in run["manifest"].values() for e in items["evidence"]})
    rows = _evidence_rows(conn, ids)
    if len(rows) != len(ids):
        out.add(FAIL, "labels", f"{len(ids) - len(rows)} evidence items the run names are missing")
        return
    answers = _answers(conn)
    same_quote_check = run["config"].get("quote_check") == quotes.VERSION
    test_run = bool(run.get("fake"))
    stand_ins = 0
    bad = 0
    for item in rows:
        eid, aid, rid, stance_, quote, _rat, mrid, source_id, locator = item
        if evidence_id(aid, rid, Stance(stance_), quote) != eid:
            out.add(FAIL, "labels", f"{eid}: its stance or quote was changed after it was stored")
            bad += 1
            continue
        rec = get_record(conn, rid)
        if rec is None or (rec.ref.source_id, rec.ref.locator) != (source_id, locator):
            out.add(FAIL, "labels", f"{eid}: its source or locator is not that of {rid}")
            bad += 1
            continue
        if _stand_in(conn, mrid, test_run):
            stand_ins += 1
        elif mrid is None:
            out.add(FAIL, "labels", f"{eid}: it names no model run, and this is not a test run")
            bad += 1
            continue
        elif not any(
            _same_label(item, a) for a in answers.get((mrid, canonical_json([aid, rid])), [])
        ):
            out.add(FAIL, "labels", f"{eid}: no stored model answer gives this label")
            bad += 1
            continue
        if same_quote_check and (
            rec.text is None
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
            f"{len(rows)} evidence items match their content and their record's source"
            + ("" if stand_ins == len(rows) else ", and the model's answers as stored"),
        )


def _ai_reviews(conn: sqlite3.Connection, out: _Out) -> None:
    """Each AI review that names a stored, well-formed reviewer answer says what it said: the
    decision and the reason, exactly (core/audit/review.py)."""
    checked = bad = 0
    for rid, status, reason, raw in conn.execute(
        "SELECT r.id, r.status, r.reason, mc.raw_output FROM evidence_reviews r"
        " JOIN model_calls mc ON mc.id = r.model_call_id"
        " WHERE r.reviewer_kind = 'ai' AND mc.outcome = 'ok' ORDER BY r.rowid"
    ):
        try:
            answer = review_mod._validate(parse_json_object(raw))
        except BadModelOutput:
            continue  # not a reviewer answer; the review then says why it failed
        checked += 1
        want = (
            EvidenceStatus.AI_ACCEPTED if answer.decision == "accept" else EvidenceStatus.DISMISSED
        )
        if (status, reason) != (want.value, answer.reason.strip()):
            out.add(FAIL, "ai reviews", f"{rid}: it is not what the reviewer's stored answer says")
            bad += 1
    if checked and not bad:
        out.add(PASS, "ai reviews", f"{checked} AI reviews say exactly what the reviewer answered")


def _expert_reviews(conn: sqlite3.Connection, out: _Out) -> None:
    """Each expert review is the one its evidence.decide entry logged: the same evidence item,
    expert, time and place in the item's reviews (the log's status and reason are compared by
    audit_log.decision_problem)."""
    bad = n = 0
    for _s, at, actor, act, p in _log(conn):
        if act != "evidence.decide":
            continue
        row = conn.execute(
            "SELECT evidence_id, seq, reviewer, decided_at_utc FROM evidence_reviews"
            " WHERE id = ? AND reviewer_kind = 'expert'",
            (p.get("review_id"),),
        ).fetchone()
        if row is None:
            continue  # decision_problem has already failed the log for this
        n += 1
        eid, seq, reviewer, decided = row
        if (
            eid != p.get("evidence_id")
            or p.get("review_id") != review_id(eid, seq)
            or reviewer != actor
            or _dt(decided) != _dt(at)
        ):
            out.add(
                FAIL,
                "expert reviews",
                f"{p.get('review_id')}: not the evidence item, expert or time the log recorded",
            )
            bad += 1
    if n and not bad:
        out.add(PASS, "expert reviews", f"{n} expert reviews are the ones the audit log recorded")


def _claims(conn: sqlite3.Connection, run: dict[str, Any], out: _Out) -> None:
    """Each audited claim is the one its audit-log entry recorded (pipeline.claim's
    claim_sha256), or what the expert's logged changes since then (claim.status) made of it."""
    log = _log(conn)
    source = run.get("evidence_from_run", run["run_id"])
    entries = {
        p["claim_id"]: (s, p)
        for s, _a, _c, act, p in log
        if act == pipeline.CLAIM_ACTION and p.get("run_id") == source
    }
    bad = unbound = edited = 0
    for claim_id in sorted(run["manifest"]):
        seq, entry = entries.get(claim_id, (None, {}))
        want = entry.get("claim_sha256")
        if seq is None or not isinstance(want, str):
            unbound += 1
            continue
        later = [
            p
            for s, _a, _c, act, p in log
            if act == "claim.status" and s > seq and p.get("claim_id") == claim_id
        ]
        rows = pipeline._stored(conn, "claims", "id = ?", (claim_id,))
        if not rows:
            out.add(FAIL, "claims", f"{claim_id}: the audited claim is missing")
            bad += 1
            continue
        row = dict(rows[0])
        if later:
            texts = [p["text"] for p in later if p.get("text") is not None]
            if row["status"] != later[-1].get("status") or (texts and row["text"] != texts[-1]):
                out.add(FAIL, "claims", f"{claim_id}: not what the expert's logged changes left")
                bad += 1
                continue
            if texts:
                if "was_text" not in later[0]:
                    edited += 1  # its text at the audit is not recorded; the logged edit binds it
                    continue
                row["text"] = later[0]["was_text"]  # the text the claim was audited with
            row["status"] = later[0].get("was")
        if pipeline._sha(canonical_json([row])) != want:
            out.add(
                FAIL, "claims", f"{claim_id}: changed after its audit, and no logged change says so"
            )
            bad += 1
    if unbound:
        out.add(NOTE, "claims", f"{unbound} audited claims predate claim digests")
    if edited:
        out.add(
            NOTE,
            "claims",
            f"{edited} claims were edited after the audit: their current text is the logged "
            "edit, but the text they were audited with is not recorded",
        )
    if not bad:
        out.add(PASS, "claims", "the audited claims are the ones the audit log recorded")


def _calls(conn: sqlite3.Connection, out: _Out) -> None:
    calls = {cid: raw for cid, raw in conn.execute("SELECT id, raw_output FROM model_calls")}
    bound: set[str] = set()
    unbound_claims = 0
    bad = False
    log = _log(conn)
    for seq, _at, _actor, action, p in log:
        if action != pipeline.CLAIM_ACTION:
            continue
        digest = p.get("model_calls")
        if not isinstance(digest, dict) or not isinstance(digest.get("ids"), list):
            unbound_claims += 1
            continue
        missing = [cid for cid in digest["ids"] if cid not in calls]
        if missing:
            out.add(FAIL, "model calls", f"entry {seq} names model call {missing[0]}, missing")
            bad = True
            continue
        if pipeline.calls_digest(conn, digest["ids"])["sha256"] != digest.get("sha256"):
            out.add(
                FAIL,
                "model calls",
                f"a model call recorded by entry {seq} was changed (its prompt, answer, "
                "outcome, subject, model run or time)",
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
    # A call a claim entry's digest names was stored by a Baker that logs each hosted answer
    # (cloud.received, from the same release as the digests); one no digest names may predate
    # both, and is only noted.
    for cid in sorted(hosted & bound):
        if _sha(calls[cid]) not in received:
            out.add(
                FAIL,
                "model calls",
                f"{cid}: this hosted model answer is not the one the API returned (cloud.received)",
            )
            bad = True
    if hosted - bound:
        out.add(
            NOTE,
            "model calls",
            f"{len(hosted - bound)} hosted model answers are named by no claim entry's digest "
            "(they predate digests and cloud.received entries), so only the evidence ids bind "
            "them",
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


def _stipulations(conn: sqlite3.Connection, out: _Out) -> None:
    """Each stored stipulation's status, decider, time and statement are what its latest
    logged expert action (stipulation.confirm or stipulation.withdraw) left them."""
    state: dict[str, tuple[str, str, str, Any]] = {}
    for _s, at, actor, act, p in _log(conn):
        if act == "stipulation.confirm":
            state[p.get("stipulation_id")] = ("confirmed", actor, at, p.get("statement"))
        elif act == "stipulation.withdraw":
            old = state.get(p.get("stipulation_id"), ("", "", "", None))
            state[p.get("stipulation_id")] = ("rejected", actor, at, old[3])
    bad = 0
    stored = pipeline.load_stipulations(conn)
    for st in stored:
        logged = state.get(st.id)
        if logged is None:
            if st.status != StipulationStatus.PROPOSED:
                out.add(FAIL, "stipulations", f"{st.id}: decided, but no expert action is logged")
                bad += 1
            continue
        status, actor, at, statement = logged
        if (
            st.status.value != status
            or st.decided_by != actor
            or st.decided_at_utc != _dt(at)
            or (statement is not None and st.statement != statement)
        ):
            out.add(FAIL, "stipulations", f"{st.id}: it is not what the logged expert action left")
            bad += 1
    if stored and not bad:
        out.add(
            PASS, "stipulations", f"{len(stored)} stipulations match the expert's logged actions"
        )


def _identity(conn: sqlite3.Connection, out: _Out) -> None:
    """Each identity link is what the logged actions left: proposed by the proposer
    (identity.propose) and undecided, or decided by the expert (identity.decide, identity.link)
    with that status, tier, expert and time; and a link the log still holds is not missing.
    Removals are logged too (identity.propose's removed, person.remove)."""
    state: dict[str, tuple[str, str | None, str | None, str | None]] = {}
    basis: dict[str, str] = {}
    for _s, at, actor, act, p in _log(conn):
        if act == links.PROPOSE_ACTION:
            for lid in p.get("added") or []:
                state.setdefault(lid, ("proposed", None, None, None))
            for lid in p.get("removed") or []:
                state.pop(lid, None)
        elif act == "identity.link":
            lid = p.get("link_id")
            state[lid] = ("confirmed", actor, at, None)
            basis.setdefault(lid, f"Linked by {actor}: {str(p.get('note', '')).strip()}")
        elif act == "identity.decide":
            state[p.get("link_id")] = (str(p.get("status")), actor, at, None)
        elif act == "person.remove":
            for lid in p.get("links_removed") or []:
                state.pop(lid, None)
    bad = 0
    stored = conn.execute(
        "SELECT id, account_id, person_id, status, tier, basis, decided_by, decided_at_utc"
        " FROM identity_links ORDER BY id"
    ).fetchall()
    for lid, aid, pid, status, tier, why, by, at in stored:
        logged = state.get(lid)
        want_tier = "confirmed" if status == "confirmed" else "inferred"
        if (
            logged is None
            or lid != links.link_id(aid, pid)
            or (status, by) != logged[:2]
            or tier != want_tier
            or (at is None) != (logged[2] is None)
            or (at is not None and _dt(at) != _dt(str(logged[2])))
            or (lid in basis and why != basis[lid])
        ):
            out.add(
                FAIL,
                "identity links",
                f"{lid}: not the account, person, status, tier, expert or time the logged "
                "actions left",
            )
            bad += 1
    gone = sorted(set(state) - {r[0] for r in stored})
    for lid in gone:
        out.add(FAIL, "identity links", f"{lid}: removed, and no logged action removed it")
        bad += 1
    if stored and not bad:
        out.add(PASS, "identity links", f"{len(stored)} identity links match the logged actions")


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
    decided_at = _decided_at(log, run)
    n = overridden = untimed = 0
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
        when = decided_at.get(claim_id)
        if when is None:
            untimed += 1
        elif problem is None and stored.decided_at_utc != _dt(when):
            problem = "its decision time is not the one the audit log recorded"
        if problem:
            out.add(FAIL, "verdicts", f"{claim_id}: {problem}")
            continue
        n += 1
        overridden += any(a == "verdict.override" for _x, a, _p in actions.get(stored.id, []))
    if untimed:
        out.add(
            NOTE,
            "verdicts",
            f"{untimed} verdicts predate logged decision times, so their times are not bound to "
            "the log",
        )
    if not out.failed("verdicts"):
        extra = f"; {overridden} then set by the expert, as logged" if overridden else ""
        out.add(PASS, "verdicts", f"the rules give all {n} verdicts exactly{extra}")


def _decided_at(log: list, run: dict[str, Any]) -> dict[str, str]:
    """Claim id -> the verdict time the audit log recorded: the claim's entry in a full audit,
    the run's entry in a verdict re-run."""
    run_id = run["run_id"]
    out: dict[str, str] = {}
    for _s, _a, _c, act, p in log:
        if p.get("run_id") != run_id or not isinstance(p.get("decided_at_utc"), str):
            continue
        if act == pipeline.CLAIM_ACTION:
            out[p["claim_id"]] = p["decided_at_utc"]
        elif act == pipeline.RUN_ACTION and run["config"].get("mode") == "rules_only":
            out.update(dict.fromkeys(run["manifest"], p["decided_at_utc"]))
    return out


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
    # The settings the audit log records, which bundle.json must also name (_manifest).
    rendered = report_html.render_report(conn, export.logged_timeline(conn))
    if rendered.encode("utf-8") != zf.read(export.REPORT):
        out.add(FAIL, "report", "the report in the bundle is not the one these tables render")
        return
    out.add(PASS, "report", "the report is exactly the one these tables render")
