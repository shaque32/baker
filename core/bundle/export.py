"""Write a case's reproducibility bundle (`mabillon export-bundle`).

Producing a bundle is the examiner's choice, made on counsel's advice: Mabillon never makes or
sends one on its own. The CLI first lists what the bundle would hold (describe()) and writes
nothing until the examiner confirms counsel reviewed it. The bundle holds the case as it stands:

    bundle.json        format, versions, build, run, scope, contents, inputs, models, audit-log
                       head, file hashes
    METHOD.md          plain-English method note: what Mabillon did, who labelled, how to check it
    report.html        the claims report, rendered from exactly the rows in tables/
    tables/<t>.jsonl   every table core/schema.sql defines, one JSON object per row, in the
                       database's own order
    withheld.jsonl     what the scope left out that a digest in the audit log names: each
                       evidence item and model call by its hash, each audit-log entry by its
                       time, actor, action and hashes (empty in a full bundle)

Scope. By default a bundle holds only what the verdicts rest on: the latest audit's
assumptions, check results and evidence items, the records they cite (with the thread and
accounts shown beside them), the model calls behind those items and their AI reviews, the
expert's decisions on them, the claims, stipulations, identity links, sources, models and
every audit-log entry but the ones listed below. Each part below is left out unless the
examiner includes it (PARTS; "all" is the whole case):

    dismissed    evidence items dismissed when their verdict was decided and still dismissed,
                 with their reviews and the expert's evidence.decide entries for them
    irrelevant   evidence items the model labelled irrelevant, likewise
    prompts      model calls no shipped item or AI review rests on, and every cloud.sent entry
                 (they hold the prompts sent)
    records      the rest of the phone: every record, thread and account no shipped row cites
    history      earlier audit runs' assumptions, checks, evidence, reviews and verdicts
    feedback     the expert's flags about Mabillon (flag.add, flag.withdraw entries)
    activity     the examiner's page views (view entries, core/review/activity.py), which name
                 the evidence items and records each page listed

No verdict rests on what a scope leaves out: the rules skip dismissed and irrelevant items
(core/audit/rules.py), and an export whose own bundle does not verify is refused. The audit
log's digests are hashes over per-item hashes (core/pipeline.py), so withheld.jsonl lets them
check without the items; a withheld log entry is kept in the chain by its hash, but what it
says cannot be checked from the bundle.

An encrypted case's bundle is encrypted under a bundle passphrase (core/bundle/sealed.py); it
is never written in plain form. Only once the file is fully written is the export logged
(bundle.export, by the expert, with the bundle's SHA-256 and the audit-log head it holds); if
that entry cannot be written, the file is removed. Only the latest completed audit can be
exported; an audit still running or stopped part way must finish first, so the bundle never
shows a verdict the rules have not finished. The zip is deterministic in layout (sorted names,
fixed timestamps). core/bundle/verify.py checks one offline, and the export runs that check on
its own bundle before writing it.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core import build, db, encryption, pipeline
from core.audit import invariants, quotes, rules
from core.bundle import sealed
from core.contracts import CONTRACTS_VERSION, EvidenceStatus, Stance, canonical_json
from core.db import apply_schema
from core.enrich.records import kind_of
from core.llm import cloud
from core.report import html as report_html
from core.review import activity, audit_log
from core.review.actions import ReviewError, _expert
from core.timeline.settings import Settings

FORMAT = "baker-reproducibility-bundle"  # a format id: keeps the development name (CLAUDE.md)
# 1.1.0: METHOD.md and the notice name the product Mabillon. 1.2.0: METHOD.md names the
# `mabillon verify-bundle` command. A minor version changes only text the exporter writes, which
# only that version's code gives again; the tables read the same.
BUNDLE_VERSION = "1.2.0"
EXPORT_ACTION = "bundle.export"
MANIFEST = "bundle.json"
METHOD = "METHOD.md"
REPORT = "report.html"
TABLES = "tables/"
WITHHELD = "withheld.jsonl"
PARTS = ("dismissed", "irrelevant", "prompts", "records", "history", "feedback", "activity")
FULL = "full"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
NOTICE = (
    "Producing this bundle is the examiner's choice, made on counsel's advice. Mabillon never "
    "makes or sends one on its own, and nothing is shared by default. The bundle holds case "
    "content (record text, prompts and model answers, the expert's reasons); it is encrypted only "
    "when the case is. Handle it under the case's protective order."
)
HOSTED = (
    "Labels from a hosted model ({vendor}, {model}). They cannot be regenerated exactly; the "
    "recorded labels and rules are reproducible."
)

Clock = Callable[[], datetime]


@dataclass
class ExportResult:
    path: Path
    sha256: str
    run_id: str
    audit_entries: int
    last_hash: str
    encrypted: bool = False
    scope: str | dict[str, Any] = FULL


def schema_tables() -> list[tuple[str, list[str]]]:
    """(table, columns) for every table core/schema.sql defines, in the order it defines them."""
    mem = sqlite3.connect(":memory:")
    try:
        apply_schema(mem)
        names = [
            r[0]
            for r in mem.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
            )
        ]
        return [(n, [c[1] for c in mem.execute(f"PRAGMA table_info({n})")]) for n in names]
    finally:
        mem.close()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _dump(
    conn: sqlite3.Connection, table: str, cols: list[str], keep: set[int] | None = None
) -> bytes:
    """The table's rows as JSON lines, in rowid order; only the rowids in `keep` when given."""
    lines = []
    sql = f"SELECT rowid, {', '.join(cols)} FROM {table} ORDER BY rowid"  # noqa: S608
    try:
        rows = conn.execute(sql).fetchall()
    except db.DatabaseError as e:  # plain SQLite or SQLCipher
        raise ReviewError(
            f"this case's {table} table does not match Mabillon's schema ({e}); a case made under "
            "an older schema cannot be exported"
        ) from e
    for rowid, *row in rows:
        if keep is not None and rowid not in keep:
            continue
        for v in row:
            if isinstance(v, bytes | bytearray | memoryview):
                raise ReviewError(f"{table} holds binary data, which a bundle cannot carry")
        lines.append(
            json.dumps(dict(zip(cols, row, strict=True)), ensure_ascii=False, sort_keys=True)
        )
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------- scope


@dataclass
class Plan:
    """What a bundle of the given scope ships and leaves out."""

    included: tuple[str, ...]
    keep: dict[str, set[int] | None]  # table -> the rowids shipped; None: every row
    withheld: list[dict[str, Any]]  # the lines of withheld.jsonl
    log: dict[int, dict[str, str]]  # withheld audit-log entries, by seq
    left_out: dict[str, int]  # rows left out, by table

    @property
    def full(self) -> bool:
        return set(PARTS) <= set(self.included)

    def scope(self) -> report_html.BundleScope | None:
        return (
            None
            if self.full
            else report_html.BundleScope(self.included, dict(self.left_out), dict(self.log))
        )

    def describe_scope(self) -> str | dict[str, Any]:
        """bundle.json's and the export entry's "scope"."""
        if self.full:
            return FULL
        return {"included": list(self.included), "left_out": dict(sorted(self.left_out.items()))}


def parts(include: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """The opt-in parts named ("all" for every one), in PARTS order. Refuses an unknown one."""
    names = include.split(",") if isinstance(include, str) else list(include or ())
    names = [n.strip() for n in names if n.strip()]
    if "all" in names:
        return PARTS
    unknown = sorted(set(names) - set(PARTS))
    if unknown:
        raise ReviewError(
            f"unknown bundle part {', '.join(unknown)}; the parts are {', '.join(PARTS)} or all"
        )
    return tuple(p for p in PARTS if p in names)


_RECORD_PARENTS = {  # a record table's columns naming another record row it is shown with
    "messages": (("thread_id", "threads"), ("sender_account_id", "accounts")),
    "calls": (("from_account_id", "accounts"), ("to_account_id", "accounts")),
    "attachments": (("message_id", "messages"),),
}
_RECORD_ROWS = (
    "messages",
    "calls",
    "contacts",
    "attachments",
    "locations",
    "threads",
    "accounts",
    "message_recipients",
    "translations",
    "exhibit_matches",
)


def _table_of(record_id: str) -> str | None:
    return pipeline._RECORD_TABLES.get(kind_of(record_id) or "") or pipeline._CHECK_TABLES.get(
        record_id.split(":", 1)[0]
    )


def _ids(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    return {str(i): r for r, i in conn.execute(f"SELECT rowid, id FROM {table}")}  # noqa: S608


def plan(conn: sqlite3.Connection, run: dict[str, Any], include: tuple[str, ...]) -> Plan:
    """The rows and entries a bundle of this scope ships, read from the case."""
    tables = [t for t, _cols in schema_tables()]
    if set(PARTS) <= set(include):
        return Plan(PARTS, dict.fromkeys(tables), [], {}, {})
    from core.bundle import verify  # imports this module

    inc = set(include)
    log = verify._log(conn)
    manifest = run["manifest"]
    runs = {run["run_id"], run.get("evidence_from_run", run["run_id"])}

    # Evidence: the audit's items, less those no verdict rests on.
    positions = verify._positions(log, run)
    left: dict[str, str] = {}
    for claim_id, items in manifest.items():
        at = verify._statuses_at(conn, log, positions[claim_id], items["evidence"])
        for e in pipeline.load_evidence(conn, items["evidence"]):
            if e.stance is Stance.IRRELEVANT and "irrelevant" not in inc:
                left[e.id] = "irrelevant"
            elif (
                "dismissed" not in inc
                and at.get(e.id) is EvidenceStatus.DISMISSED
                and e.status is EvidenceStatus.DISMISSED
            ):
                left[e.id] = "dismissed"
    named = {
        key: {i for items in manifest.values() for i in items[key]}
        for key in ("assumptions", "checks", "evidence")
    }
    history = "history" in inc
    keep_ids = {
        "assumptions": None if history else named["assumptions"],
        "check_results": None if history else named["checks"],
        "evidence_items": None if history else named["evidence"] - set(left),
    }
    if history:
        keep_ids["evidence_items"] = set(_ids(conn, "evidence_items")) - set(left)
    keep: dict[str, set[int] | None] = dict.fromkeys(tables)
    for table, ids in keep_ids.items():
        rowids = _ids(conn, table)
        keep[table] = {r for i, r in rowids.items() if ids is None or i in ids}
    kept_ev = {i for i, r in _ids(conn, "evidence_items").items() if r in keep["evidence_items"]}
    reviews = [
        (r, eid, call)
        for r, eid, call in conn.execute(
            "SELECT rowid, evidence_id, model_call_id FROM evidence_reviews"
        )
    ]
    keep["evidence_reviews"] = {r for r, eid, _c in reviews if eid in kept_ev}
    if not history:
        for table in ("verdicts", "run_claims"):
            keep[table] = {
                r
                for r, rid in conn.execute(f"SELECT rowid, pipeline_run_id FROM {table}")  # noqa: S608
                if rid in runs
            }

    # Model calls: the answers the shipped items and AI reviews rest on.
    calls = _ids(conn, "model_calls")
    if "prompts" not in inc:
        behind: set[str] = {str(c) for _r, eid, c in reviews if eid in kept_ev and c}
        for e in pipeline.load_evidence(conn, sorted(kept_ev)):
            behind.update(
                cid
                for (cid,) in conn.execute(
                    "SELECT id FROM model_calls WHERE model_run_id = ? AND subject_json = ?"
                    " AND outcome = 'ok'",
                    (e.model_run_id, canonical_json([e.assumption_id, e.record_id])),
                )
            )
        keep["model_calls"] = {r for i, r in calls.items() if i in behind}

    # Records: those the shipped rows cite, with the rows shown beside them.
    if "records" not in inc:
        want: dict[str, set[str]] = defaultdict(set)
        ev_rows = conn.execute("SELECT rowid, record_id FROM evidence_items").fetchall()
        cited = [str(rid) for r, rid in ev_rows if r in keep["evidence_items"]]
        ck_keep = keep["check_results"]
        for r, ids_json in conn.execute("SELECT rowid, record_ids_json FROM check_results"):
            if ck_keep is None or r in ck_keep:
                cited += [str(x) for x in json.loads(ids_json or "[]")]
        for rid in cited:
            table = _table_of(rid)
            if table:
                want[table].add(rid)
        want["accounts"].update(
            str(a) for (a,) in conn.execute("SELECT account_id FROM identity_links")
        )
        for table in ("attachments", "messages", "calls"):  # children before their parents
            cols = _RECORD_PARENTS[table]
            for row in conn.execute(
                f"SELECT id, {', '.join(c for c, _t in cols)} FROM {table}"  # noqa: S608
            ):
                if row[0] in want[table]:
                    for (_c, parent), val in zip(cols, row[1:], strict=True):
                        if val is not None:
                            want[parent].add(str(val))
        for table in ("messages", "calls", "contacts", "attachments", "threads", "accounts"):
            keep[table] = {r for i, r in _ids(conn, table).items() if i in want[table]}
        for table in ("locations", "message_recipients", "translations"):
            keep[table] = set()
        keep["exhibit_matches"] = {
            r
            for r, rid in conn.execute("SELECT rowid, record_id FROM exhibit_matches")
            if rid in want["messages"]
        }

    # The audit log: every entry, less those about rows left out.
    withheld_log: dict[int, dict[str, str]] = {}
    for seq, at, actor, action, p in log:
        why = None
        if action == "cloud.sent" and "prompts" not in inc:
            why = "prompts"
        elif action == "evidence.decide" and p.get("evidence_id") not in kept_ev:
            why = left.get(str(p.get("evidence_id")), "history")
        elif action.startswith("flag.") and "feedback" not in inc:
            why = "feedback"
        elif action == activity.VIEW and "activity" not in inc:
            why = "activity"
        if why is not None:
            prev, h = conn.execute(
                "SELECT prev_hash, hash FROM audit_log WHERE seq = ?", (seq,)
            ).fetchone()
            withheld_log[seq] = {
                "at_utc": at,
                "actor": actor,
                "action": action,
                "prev_hash": prev,
                "hash": h,
            }
    keep["audit_log"] = {
        r for r, seq in conn.execute("SELECT rowid, seq FROM audit_log") if seq not in withheld_log
    }

    # What the log's digests name and the bundle leaves out, by hash.
    lines: list[dict[str, Any]] = [
        {"kind": "evidence", "id": eid, "why": why, "sha256": pipeline.evidence_sha256(conn, eid)}
        for eid, why in sorted(left.items())
    ]
    kept_calls = keep["model_calls"]
    if kept_calls is not None:
        digested = {
            cid
            for _s, _a, _c, act, p in log
            if act == pipeline.CLAIM_ACTION
            for cid in entry_calls(p)
        }
        lines += [
            {"kind": "model_call", "id": cid, "sha256": pipeline.call_sha256(conn, cid)}
            for cid in sorted(digested)
            if cid in calls and calls[cid] not in kept_calls
        ]
    lines += [
        {"kind": "audit_log", "seq": seq, **stub} for seq, stub in sorted(withheld_log.items())
    ]
    left_out = {}
    for table in tables:
        if keep[table] is not None:
            total = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
            if total - len(keep[table]):
                left_out[table] = total - len(keep[table])
    return Plan(tuple(include), keep, lines, withheld_log, left_out)


def _inputs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    importers = {
        sid: (imp, ver)
        for sid, imp, ver in _rows(
            conn, "SELECT source_id, importer, importer_version FROM source_coverage"
        )
    }
    out = []
    for sid, kind, fidelity, name, sha, tool, tool_ver, imported in _rows(
        conn,
        "SELECT id, kind, fidelity, file_name, sha256, tool_name, tool_version, imported_at_utc"
        " FROM sources ORDER BY id",
    ):
        imp = importers.get(sid)
        out.append(
            {
                "source_id": sid,
                "kind": kind,
                "fidelity": fidelity,
                "file_name": name,
                "sha256": sha,
                "tool": tool,
                "tool_version": tool_ver,
                "imported_at_utc": imported,
                "importer": imp[0] if imp else None,
                "importer_version": imp[1] if imp else None,
            }
        )
    return out


def _case_copies(items: list[dict[str, Any]], inputs_dir: Path) -> None:
    """Mark whether the case's own copy of each input still hashes to what was imported. An
    encrypted case's copies are read back through decryption (they hold ciphertext); a copy
    that cannot be read is marked None, not checked, never False."""
    on_disk: set[str] = set()
    unreadable = False
    if inputs_dir.is_dir():
        for p in sorted(inputs_dir.rglob("*")):
            if p.is_file():
                try:
                    on_disk.add(encryption.plain_sha256(p))
                except (OSError, encryption.EncryptionError, encryption.CaseLocked):
                    unreadable = True
    for item in items:
        found = item["sha256"] in on_disk
        item["case_copy_matches_at_export"] = True if found else (None if unreadable else False)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def model_identity(row: dict[str, Any]) -> dict[str, Any]:
    """One model run as the bundle and the method note describe it."""
    params = json.loads(row["params_json"])
    hosted = cloud.is_cloud_sha(row["model_sha256"])
    out: dict[str, Any] = {
        "model_run_id": row["id"],
        "purpose": row["purpose"],
        "model_name": row["model_name"],
        "where": "cloud" if hosted else "local",
        "prompt_version": row["prompt_version"],
        "prompt_sha256": row["prompt_sha256"],
        "params": params,
    }
    if hosted:
        out["vendor"] = "Anthropic"
        out["api_model"] = params.get("api_model", row["model_name"])
        out["effort"] = params.get("effort")
        out["disclosure"] = HOSTED.format(vendor="Anthropic", model=out["api_model"])
    else:
        out["model_file_sha256"] = row["model_sha256"]
        out["seed"] = row["seed"]
        out["stand_in"] = bool(params.get("stand_in"))
    return out


def models(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every model run of the case, as bundle.json lists them (model_identity)."""
    cols = [
        "id",
        "purpose",
        "model_name",
        "model_sha256",
        "prompt_version",
        "prompt_sha256",
        "params_json",
        "seed",
    ]
    return [
        model_identity(dict(zip(cols, r, strict=True)))
        for r in _rows(conn, f"SELECT {', '.join(cols)} FROM model_runs ORDER BY rowid")  # noqa: S608
    ]


def run_info(run: dict[str, Any]) -> dict[str, Any]:
    """The exported audit run, as bundle.json describes it."""
    return {
        "run_id": run["run_id"],
        "mode": run["config"].get("mode", "full"),
        "evidence_from_run": run.get("evidence_from_run", run["run_id"]),
        "started_at_utc": run["started_at_utc"],
        "pipeline": run["baker_version"],
        "contracts_version": run["contracts_version"],
        "rule_version": run["rule_version"],
        "quote_check": run["config"].get("quote_check"),
        "build": run["config"].get("build"),
        "evidence_build": run["config"].get("evidence_build", run["config"].get("build")),
        "cloud": run["config"].get("cloud"),
        "test_run": bool(run.get("fake")),
        "claims": len(run["manifest"]),
    }


def logged_timeline(conn: sqlite3.Connection) -> Settings:
    """The timeline settings as the audit log records them: the defaults, then each expert
    change (timeline.settings, core/timeline/settings.py) in order."""
    tol, gap = Settings().tolerance_min, Settings().gap_hours
    for (payload,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'timeline.settings' ORDER BY seq"
    ):
        p = json.loads(payload)
        tol, gap = int(p["tolerance_min"][1]), int(p["gap_hours"][1])
    return Settings(tol, gap)


def withheld_log(withheld: list[dict[str, Any]]) -> dict[int, dict[str, str]]:
    """The audit-log entries withheld.jsonl lists, by seq."""
    return {
        int(w["seq"]): {k: w.get(k) for k in ("at_utc", "actor", "action", "prev_hash", "hash")}
        for w in withheld
        if w.get("kind") == "audit_log"
    }


def withheld_known(withheld: list[dict[str, Any]]) -> dict[str, str]:
    """Evidence item and model call id -> the hash withheld.jsonl lists for it."""
    return {
        str(w["id"]): str(w["sha256"])
        for w in withheld
        if w.get("kind") in ("evidence", "model_call")
    }


def derived(
    conn: sqlite3.Connection, run: dict[str, Any], withheld: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """The parts of bundle.json that follow from the tables and withheld.jsonl alone, so
    core/bundle/verify.py recomputes them and requires an exact match."""
    withheld = withheld or []
    heads = _rows(conn, "SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1")
    heads += [(seq, w["hash"]) for seq, w in withheld_log(withheld).items()]
    seq, last = max(heads)
    tl = logged_timeline(conn)
    kinds = [str(w.get("kind")) for w in withheld]
    return {
        "contents": contents(conn),
        "run": run_info(run),
        "inputs": _inputs(conn),
        "models": models(conn),
        "timeline_settings": {"tolerance_min": tl.tolerance_min, "gap_hours": tl.gap_hours},
        "audit_log": {"entries": seq, "last_seq": seq, "last_hash": last},
        "withheld": {k: kinds.count(k) for k in ("evidence", "model_call", "audit_log")},
    }


def claim_entries(conn: sqlite3.Connection, run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Claim id -> the pipeline.claim entry that wrote the rows the run's verdict for it rests
    on: the run's own entries, or for a verdict re-run, those of the audit its evidence came
    from. The latest such entry per claim."""
    source = run.get("evidence_from_run", run["run_id"])
    return {
        p["claim_id"]: p
        for p in pipeline.finished_claims(conn, source)
        if p["claim_id"] in run["manifest"]
    }


def entry_calls(entry: dict[str, Any]) -> list[str]:
    """The model calls a claim entry names (pipeline.claim's model_calls)."""
    digest = entry.get("model_calls")
    ids = digest.get("ids") if isinstance(digest, dict) else None
    return [str(i) for i in ids] if isinstance(ids, list) else []


def changed_rows(
    conn: sqlite3.Connection, run: dict[str, Any], known: dict[str, str] | None = None
) -> tuple[list[str], int]:
    """(claims whose rows differ from the digest their claim entry recorded, claims whose entry
    records no digest). A row differs when it was edited after its claim was decided. `known`:
    the hashes of evidence items a scoped bundle left out (withheld.jsonl)."""
    changed, unbound = [], 0
    for claim_id, entry in sorted(claim_entries(conn, run).items()):
        want = entry.get("rows_sha256")
        if not isinstance(want, str):
            unbound += 1
        elif pipeline.rows_digest(conn, entry["manifest"], claim_id, known) != want:
            changed.append(claim_id)
    return changed, unbound


def contents(conn: sqlite3.Connection) -> dict[str, int]:
    """What a bundle of this case holds: every table and its row count. The export names it
    before the examiner confirms, and bundle.json and the export's log entry record it."""
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
        for table, _cols in schema_tables()
    }


def describe(counts: dict[str, int], scope: Plan | None = None) -> str:
    """What the bundle will hold, in plain words, for the confirmation."""
    rows = ", ".join(f"{t} {n}" for t, n in counts.items() if n)
    if scope is None or scope.full:
        return (
            "The bundle will hold the whole case: every table (rows: " + rows + "), including "
            "every record imported from the phones, every prompt sent to a model and its answer, "
            "every evidence item (dismissed ones too) with the expert's reasons, the AI "
            "reviewer's output, the full audit log, the report and a method note."
        )
    shipped = ", ".join(
        f"{t} {n - scope.left_out.get(t, 0)}"
        for t, n in counts.items()
        if n - scope.left_out.get(t, 0)
    )
    out = [p for p in PARTS if p not in scope.included]
    return (
        "The bundle will hold what the latest audit's verdicts rest on (rows: " + shipped + "): "
        "the claims, the assumptions, checks and evidence items behind each verdict, the records "
        "they cite, the model answers behind those items with their prompts, the expert's "
        "decisions and reasons on them, stipulations, identity links, sources, models, the "
        "audit log (entries about rows left out are kept as hashes only), the report and a "
        "method note. Left out unless you include them (--include): "
        + "; ".join(f"{p}: {report_html.SCOPE_PARTS[p]}" for p in out)
        + ". The prompts shipped still quote the nearby messages the model was shown."
    )


def preview(conn: sqlite3.Connection, include: tuple[str, ...]) -> str:
    """describe() for an export of this scope, read from the case as it stands."""
    run = pipeline.view_run(conn)
    if run is None or run.get("partial"):
        return describe(contents(conn))
    return describe(contents(conn), plan(conn, run, include))


def _build(
    conn: sqlite3.Connection,
    actor: str,
    encrypted_case: bool,
    passphrase: str | None,
    timeline: Settings | None,
    inputs_dir: Path | None,
    clock: Clock | None,
    include: tuple[str, ...],
) -> tuple[bytes, dict[str, Any], dict[str, Any], dict[str, int], Plan, datetime]:
    """(the bundle's bytes, run, audit-log head, contents, scope, export time), read from the
    case inside export_bundle's transaction. Refuses what cannot be exported."""
    run, last = pipeline.view_run(conn), pipeline.last_run(conn)
    if last is None:
        raise ReviewError("no completed audit to export; run the audit first")
    if (
        run is None
        or run.get("partial")
        or run["run_id"] != last["run_id"]
        or pipeline.latest_attempt(conn) is not None
    ):
        raise ReviewError(
            "a newer audit is running or has not finished; let it finish, or resume it, before "
            "exporting, so the bundle shows only verdicts the rules finished"
        )
    if (run["rule_version"], run["contracts_version"]) != (rules.RULE_VERSION, CONTRACTS_VERSION):
        raise ReviewError(
            f"the latest audit was decided under rules {run['rule_version']} and contracts "
            f"{run['contracts_version']}; this Mabillon has rules {rules.RULE_VERSION} and "
            f"contracts {CONTRACTS_VERSION}, so its bundle could not be verified here. Re-run the "
            "verdicts or the full audit first"
        )
    changed, _unbound = changed_rows(conn, run)
    if changed:
        raise ReviewError(
            "the stored rows behind "
            + ", ".join(changed)
            + " are no longer the ones their verdicts were decided on (an audit that did not "
            "finish rewrote them); run the full audit again before exporting"
        )
    logged = logged_timeline(conn)
    if timeline is not None and timeline != logged:
        raise ReviewError(
            "the case's timeline settings are not the ones its audit log records; set them again "
            "on the Timeline page before exporting"
        )
    now = (clock or (lambda: datetime.now(UTC)))()
    scope = plan(conn, run, include)

    files: dict[str, bytes] = {}
    for table, cols in schema_tables():
        files[f"{TABLES}{table}.jsonl"] = _dump(conn, table, cols, scope.keep[table])
    files[WITHHELD] = _jsonl(scope.withheld)
    # Everything below is read from the bundle's own rows, as core/bundle/verify.py reads them.
    mem = load(files)
    try:
        facts = derived(mem, run, scope.withheld)
        report = report_html.render_report(mem, logged, scope.scope())
    finally:
        mem.close()
    invariants.check_report_text(report)
    files[REPORT] = report.encode("utf-8")
    if inputs_dir is not None:
        _case_copies(facts["inputs"], inputs_dir)

    manifest: dict[str, Any] = {
        "format": FORMAT,
        "bundle_version": BUNDLE_VERSION,
        "created_at_utc": pipeline.iso(now),
        "created_by": actor,
        "notice": NOTICE,
        "scope": scope.describe_scope(),
        "counsel_confirmed": True,
        "exported_with": {
            "build": build.build_info(),
            "pipeline": pipeline.PIPELINE_VERSION,
            "contracts": CONTRACTS_VERSION,
            "rules": rules.RULE_VERSION,
            "report": report_html.REPORT_VERSION,
            "quote_check": quotes.VERSION,
        },
        **facts,
    }
    files[METHOD] = method_note(manifest).encode("utf-8")
    manifest["files"] = {
        name: {"sha256": sha256(data), "bytes": len(data)} for name, data in sorted(files.items())
    }
    files[MANIFEST] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    data = buf.getvalue()
    _self_check(data)
    if encrypted_case:
        assert passphrase is not None  # noqa: S101 - checked by export_bundle
        data = sealed.seal(data, passphrase)
    return data, run, facts["audit_log"], facts["contents"], scope, now


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def load(files: dict[str, bytes]) -> sqlite3.Connection:
    """A database in memory holding a bundle's tables (tables/<t>.jsonl), as core/bundle/
    verify.py loads them: foreign keys off while loading. Raises on a row that does not fit."""
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    for table, cols in schema_tables():
        rows = [json.loads(line) for line in files[f"{TABLES}{table}.jsonl"].decode().splitlines()]
        conn.executemany(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",  # noqa: S608
            [tuple(r[c] for c in cols) for r in rows],
        )
    return conn


def _self_check(data: bytes) -> None:
    """Refuse a bundle that does not pass Mabillon's own offline check: a scope that left out a
    row a verdict rests on, or a case whose rows the export's checks above did not catch."""
    from core.bundle import verify  # imports this module

    fails = [f for f in verify.verify_data(data) if f.level == verify.FAIL]
    if fails:
        raise ReviewError(
            "the bundle would not pass verify-bundle ("
            + "; ".join(f"{f.check}: {f.detail}" for f in fails[:3])
            + "); nothing was written. Export the whole case with --include all, or report this "
            "as a Mabillon fault"
        )


def _publish(out: Path, data: bytes) -> None:
    """Write `out` whole or not at all, and never over a file already there, even one another
    export created a moment ago: the bytes go to a temporary file of this export's own, which is
    then hard-linked to `out` (refused if `out` exists). On a file system without hard links
    (some USB drives), `out` is first created empty and exclusively, then the temporary file
    replaces it in one rename."""
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".partial", dir=out.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, out)
        except FileExistsError:
            raise ReviewError(f"{out} already exists; choose a new file name") from None
        except OSError:
            try:
                open(out, "xb").close()  # claim the name; only this export may replace it
            except FileExistsError:
                raise ReviewError(f"{out} already exists; choose a new file name") from None
            try:
                os.replace(tmp, out)  # whole: the claimed name never holds a partial bundle
            except BaseException:
                out.unlink(missing_ok=True)
                raise
    finally:
        tmp.unlink(missing_ok=True)


def export_bundle(
    conn: sqlite3.Connection,
    out: Path,
    actor: str,
    *,
    counsel_confirmed: bool,
    encrypted_case: bool = False,
    passphrase: str | None = None,
    timeline: Settings | None = None,
    inputs_dir: Path | None = None,
    clock: Clock | None = None,
    include: str | list[str] | tuple[str, ...] | None = None,
) -> ExportResult:
    """Write the bundle for the latest completed audit to `out` (a new file). The caller has
    already checked the audit log (core/review/audit_log.require_intact), as every path that
    opens a case does.

    Never by default: `counsel_confirmed` must say the examiner confirmed, on counsel's review,
    exporting exactly what describe() lists. `include`: the opt-in parts (PARTS, or "all");
    by default the bundle holds only what the verdicts rest on (the module's docstring). An
    encrypted case's bundle is sealed under
    `passphrase` (core/bundle/sealed.py); without one it is refused, never written in plain
    form. The export is logged (bundle.export, with the bundle's SHA-256) only after the file
    is fully written; if that entry cannot be written the file is removed, so a failed export
    leaves neither a bundle nor a success entry."""
    _expert(actor)
    chosen = parts(include)
    if not counsel_confirmed:
        raise ReviewError(
            "a bundle is exported only after the examiner confirms, on counsel's review, what it "
            "holds; nothing was written"
        )
    if encrypted_case and not passphrase:
        raise ReviewError(
            "this case is encrypted, so its bundle must be encrypted too: give a bundle "
            "passphrase; nothing was written"
        )
    out = Path(out)
    if out.exists():
        raise ReviewError(f"{out} already exists; choose a new file name")
    try:
        # One write transaction from the first read to the bundle.export entry: the bundle is
        # one snapshot of the case, and no decision the screen records can land between the
        # rows it holds and the entry that logs it (the screen waits for the export).
        conn.execute("BEGIN IMMEDIATE")
    except db.DatabaseError as e:
        raise ReviewError(
            f"the case is busy saving something else ({e}); try the export again in a moment"
        ) from e
    published = False
    try:
        data, run, head, counts, scope, now = _build(
            conn, actor, encrypted_case, passphrase, timeline, inputs_dir, clock, chosen
        )
        bundle_sha = sha256(data)
        _publish(out, data)
        published = True
        audit_log.append(
            conn,
            now,
            actor,
            EXPORT_ACTION,
            {
                "format": FORMAT,
                "bundle_version": BUNDLE_VERSION,
                "file_name": out.name,
                "bundle_sha256": bundle_sha,
                "encrypted": encrypted_case,
                "counsel_confirmed": True,
                "scope": scope.describe_scope(),
                "contents": counts,
                "run_id": run["run_id"],
                "audit_log_head": {"seq": head["last_seq"], "hash": head["last_hash"]},
            },
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        if published:
            out.unlink(missing_ok=True)  # an export the log does not record is not left behind
        raise
    return ExportResult(
        path=out,
        sha256=bundle_sha,
        run_id=run["run_id"],
        audit_entries=head["last_seq"],
        last_hash=head["last_hash"],
        encrypted=encrypted_case,
        scope=scope.describe_scope(),
    )


def labelled_by(manifest: dict[str, Any]) -> list[str]:
    """One plain line per model that labelled evidence or did other model work in the case."""
    lines = []
    for m in manifest["models"]:
        if m["where"] == "cloud":
            lines.append(
                f"- {m['purpose']}: {m['disclosure']} Effort: {m.get('effort')}. Prompt "
                f"{m['prompt_version']}. Mabillon logs each request and answer (cloud.sent, "
                "cloud.received: the API's message and request ids); answers stored before it "
                "did are listed as NOT VERIFIED by verify-bundle."
            )
        elif m.get("stand_in"):
            lines.append(
                f"- {m['purpose']}: a test stand-in ({m['model_name']}), not a model. Nothing it "
                "labelled is a finding."
            )
        else:
            lines.append(
                f"- {m['purpose']}: local model {m['model_name']}, file SHA-256 "
                f"{m['model_file_sha256']}, seed {m['seed']}, settings in bundle.json, prompt "
                f"{m['prompt_version']}."
            )
    return lines or ["- No model ran in this case."]


def scope_lines(manifest: dict[str, Any]) -> list[str]:
    """What the bundle holds and leaves out, for the method note."""
    scope = manifest["scope"]
    if scope == FULL:
        return ["The whole case: every row of every table and every audit-log entry."]
    left = [p for p in PARTS if p not in scope["included"]]
    w = manifest["withheld"]
    return [
        "What the latest audit's verdicts rest on, chosen by the examiner. Left out:",
        "",
        *(f"- {p}: {report_html.SCOPE_PARTS[p]}." for p in left),
        "",
        f"Rows left out, by table: {', '.join(f'{t} {n}' for t, n in scope['left_out'].items())}"
        ". withheld.jsonl lists, by SHA-256, the "
        f"{w['evidence']} evidence items and {w['model_call']} model calls left out that the "
        f"audit log's digests name, and the {w['audit_log']} audit-log entries left out, by "
        "time, actor, action and hash, so the hash chain and every digest still check. No "
        "verdict rests on what was left out, and Mabillon refused to write this bundle unless "
        "verify-bundle passed it. What a left-out entry or row says cannot be checked from "
        "this bundle, and a left-out entry's time, actor and action are as the export listed "
        "them; the full case, or a bundle exported with --include all, can show each one.",
    ]


def method_note(manifest: dict[str, Any]) -> str:
    run, built = manifest["run"], manifest["run"].get("build") or {}
    commit = built.get("commit", build.NOT_RECORDED)
    test = (
        "\n**This is a test run with stand-in components. Nothing in it is a finding.**\n"
        if run["test_run"]
        else ""
    )
    return "\n".join(
        [
            "# Method note",
            "",
            f"Reproducibility bundle {manifest['bundle_version']}, exported "
            f"{manifest['created_at_utc']} by {manifest['created_by']}.",
            test,
            manifest["notice"],
            "",
            "## Scope",
            "",
            *scope_lines(manifest),
            "",
            "## What Mabillon did",
            "",
            "1. Imported each file listed under `inputs` in bundle.json, read-only, and recorded "
            "its SHA-256.",
            "2. Split the government document into claims; the expert accepted, edited or wrote "
            "each one (tables/claims.jsonl, audit log).",
            "3. For each claim, filled fixed assumption templates, ran deterministic checks, and "
            "retrieved candidate records.",
            "4. A model labelled each (assumption, record) pair: supports, contradicts, "
            "complicates or irrelevant, with a quote. Code checked every quote word for word "
            "against the record; a label whose quote failed was dropped and kept only in "
            "tables/model_calls.jsonl (outcome quote_failed).",
            f"5. Versioned rules ({run['rule_version']}, code, not a model) decided each verdict "
            "from the labels, the checks and the expert's decisions. Nothing is supported until "
            'the expert accepts its supporting evidence, and a model\'s "contradicts" counts only '
            "once the expert accepts it.",
            "6. The expert's decisions, each with a typed reason, are in "
            "tables/evidence_reviews.jsonl and in the hash-chained audit log.",
            "",
            "## Who labelled the evidence",
            "",
            *labelled_by(manifest),
            "",
            "## How to check this bundle",
            "",
            f"- Offline, with Mabillon at commit {commit} (rules {run['rule_version']}): "
            "`mabillon verify-bundle <this zip> [--inputs <folder holding the original files>]`. "
            "It checks every file's hash, the audit log's hash chain, that each label matches the "
            "model's answer as stored, and re-applies the rules to the recorded labels and "
            "expert decisions; every verdict must come out exactly as recorded.",
            "- Without Mabillon: every table is JSON lines. Each audit-log entry's hash is the "
            "SHA-256 of the JSON array [prev_hash, at_utc, actor, action, payload_json] "
            "(core/review/audit_log.py).",
            f"- The audit log's last hash is {manifest['audit_log']['last_hash']}. The report in "
            "this bundle prints it; compare it with any report produced separately.",
            "",
            "## Limits",
            "",
            "- A hosted model's labels cannot be regenerated exactly; the recorded labels and the "
            "rules applied to them are what can be re-checked.",
            "- Regenerating a local model's labels needs the same model file, runtime and "
            "settings; Mabillon has not tested that across machines.",
            '- "Not found" never means "did not happen": an absence finding states what was '
            "searched and what the source could show.",
            "- The tamper check is as strong as its anchor: the last hash above, printed on the "
            "report. There is no signature or outside timestamp.",
            "",
        ]
    )
