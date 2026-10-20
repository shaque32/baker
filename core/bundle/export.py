"""Write a case's reproducibility bundle (`baker export-bundle`).

Producing a bundle is the examiner's choice, made on counsel's advice: Baker never makes or
sends one on its own. The CLI first lists what the bundle would hold (describe()) and writes
nothing until the examiner confirms counsel reviewed it. The bundle holds the case as it stands:

    bundle.json        format, versions, build, run, contents, inputs, models, audit-log head,
                       file hashes
    METHOD.md          plain-English method note: what Baker did, who labelled, how to check it
    report.html        the claims report, rendered from exactly the rows in tables/
    tables/<t>.jsonl   every table core/schema.sql defines, one JSON object per row, in the
                       database's own order: model calls with prompt and raw output as stored,
                       evidence items, expert reviews, verdicts, the full audit log

An encrypted case's bundle is encrypted under a bundle passphrase (core/bundle/sealed.py); it
is never written in plain form. Only once the file is fully written is the export logged
(bundle.export, by the expert, with the bundle's SHA-256 and the audit-log head it holds); if
that entry cannot be written, the file is removed. Only the latest completed audit can be
exported; an audit still running or stopped part way must finish first, so the bundle never
shows a verdict the rules have not finished. The zip is deterministic in layout (sorted names,
fixed timestamps). core/bundle/verify.py checks one offline.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core import build, db, encryption, pipeline
from core.audit import invariants, quotes, rules
from core.bundle import sealed
from core.contracts import CONTRACTS_VERSION
from core.db import apply_schema
from core.llm import cloud
from core.report import html as report_html
from core.review import audit_log
from core.review.actions import ReviewError, _expert
from core.timeline.settings import Settings

FORMAT = "baker-reproducibility-bundle"
BUNDLE_VERSION = "1.0.0"
EXPORT_ACTION = "bundle.export"
MANIFEST = "bundle.json"
METHOD = "METHOD.md"
REPORT = "report.html"
TABLES = "tables/"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
NOTICE = (
    "Producing this bundle is the examiner's choice, made on counsel's advice. Baker never makes "
    "or sends one on its own, and nothing is shared by default. The bundle holds case content "
    "(record text, prompts and model answers, the expert's reasons); it is encrypted only when "
    "the case is. Handle it under the case's protective order."
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
    files: dict[str, str] = field(default_factory=dict)  # name -> sha256
    encrypted: bool = False


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


def _dump(conn: sqlite3.Connection, table: str, cols: list[str]) -> bytes:
    lines = []
    sql = f"SELECT {', '.join(cols)} FROM {table} ORDER BY rowid"  # noqa: S608 - schema names
    try:
        rows = conn.execute(sql).fetchall()
    except db.DatabaseError as e:  # plain SQLite or SQLCipher
        raise ReviewError(
            f"this case's {table} table does not match Baker's schema ({e}); a case made under "
            "an older schema cannot be exported"
        ) from e
    for row in rows:
        for v in row:
            if isinstance(v, bytes | bytearray | memoryview):
                raise ReviewError(f"{table} holds binary data, which a bundle cannot carry")
        lines.append(
            json.dumps(dict(zip(cols, row, strict=True)), ensure_ascii=False, sort_keys=True)
        )
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    return conn.execute(sql, params).fetchall()


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


def derived(conn: sqlite3.Connection, run: dict[str, Any]) -> dict[str, Any]:
    """The parts of bundle.json that follow from the tables alone, so core/bundle/verify.py
    recomputes them and requires an exact match."""
    seq, last = _rows(conn, "SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1")[0]
    return {
        "contents": contents(conn),
        "run": run_info(run),
        "inputs": _inputs(conn),
        "models": models(conn),
        "audit_log": {"entries": seq, "last_seq": seq, "last_hash": last},
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


def changed_rows(conn: sqlite3.Connection, run: dict[str, Any]) -> tuple[list[str], int]:
    """(claims whose rows differ from the digest their claim entry recorded, claims whose entry
    records no digest). A row differs when it was edited after its claim was decided."""
    changed, unbound = [], 0
    for claim_id, entry in sorted(claim_entries(conn, run).items()):
        want = entry.get("rows_sha256")
        if not isinstance(want, str):
            unbound += 1
        elif pipeline.rows_digest(conn, entry["manifest"]) != want:
            changed.append(claim_id)
    return changed, unbound


def contents(conn: sqlite3.Connection) -> dict[str, int]:
    """What a bundle of this case holds: every table and its row count. The export names it
    before the examiner confirms, and bundle.json and the export's log entry record it."""
    return {
        table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
        for table, _cols in schema_tables()
    }


def describe(counts: dict[str, int]) -> str:
    """The contents in plain words, for the confirmation."""
    rows = ", ".join(f"{t} {n}" for t, n in counts.items() if n)
    return (
        "The bundle will hold the whole case: every table (rows: " + rows + "), including every "
        "record imported from the phones, every prompt sent to a model and its answer, every "
        "evidence item (dismissed ones too) with the expert's reasons, the AI reviewer's output, "
        "the full audit log, the report and a method note."
    )


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
) -> ExportResult:
    """Write the bundle for the latest completed audit to `out` (a new file). The caller has
    already checked the audit log (core/review/audit_log.require_intact), as every path that
    opens a case does.

    Never by default: `counsel_confirmed` must say the examiner confirmed, on counsel's review,
    exporting exactly what describe() lists. An encrypted case's bundle is sealed under
    `passphrase` (core/bundle/sealed.py); without one it is refused, never written in plain
    form. The export is logged (bundle.export, with the bundle's SHA-256) only after the file
    is fully written; if that entry cannot be written the file is removed, so a failed export
    leaves neither a bundle nor a success entry."""
    _expert(actor)
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
    changed, _unbound = changed_rows(conn, run)
    if changed:
        raise ReviewError(
            "the stored rows behind "
            + ", ".join(changed)
            + " are no longer the ones their verdicts were decided on (an audit that did not "
            "finish rewrote them); run the full audit again before exporting"
        )
    timeline = timeline or Settings()
    now = (clock or (lambda: datetime.now(UTC)))()
    facts = derived(conn, run)
    counts = facts["contents"]
    head = facts["audit_log"]

    files: dict[str, bytes] = {}
    for table, cols in schema_tables():
        files[f"{TABLES}{table}.jsonl"] = _dump(conn, table, cols)
    report = report_html.render_report(conn, timeline)
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
        "scope": "full",
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
        "timeline_settings": {
            "tolerance_min": timeline.tolerance_min,
            "gap_hours": timeline.gap_hours,
        },
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
    if encrypted_case:
        assert passphrase is not None  # noqa: S101 - checked above
        data = sealed.seal(data, passphrase)
    bundle_sha = sha256(data)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.name}.partial")
    try:
        with open(tmp, "xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:
        with conn:
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
                    "scope": "full",
                    "contents": counts,
                    "run_id": run["run_id"],
                    "audit_log_head": {"seq": head["last_seq"], "hash": head["last_hash"]},
                },
            )
    except BaseException:
        out.unlink(missing_ok=True)  # an export the log does not record is not left behind
        raise
    return ExportResult(
        path=out,
        sha256=bundle_sha,
        run_id=run["run_id"],
        audit_entries=head["last_seq"],
        last_hash=head["last_hash"],
        files={name: sha256(d) for name, d in files.items()},
        encrypted=encrypted_case,
    )


def labelled_by(manifest: dict[str, Any]) -> list[str]:
    """One plain line per model that labelled evidence or did other model work in the case."""
    lines = []
    for m in manifest["models"]:
        if m["where"] == "cloud":
            lines.append(
                f"- {m['purpose']}: {m['disclosure']} Effort: {m.get('effort')}. Prompt "
                f"{m['prompt_version']}. Each request and answer is in the audit log "
                "(cloud.sent, cloud.received: the API's message and request ids)."
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
            "## What Baker did",
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
            f"- Offline, with Baker at commit {commit} (rules {run['rule_version']}): "
            "`baker verify-bundle <this zip> [--inputs <folder holding the original files>]`. It "
            "checks every file's hash, the audit log's hash chain, that each label matches the "
            "model's answer as stored, and re-applies the rules to the recorded labels and "
            "expert decisions; every verdict must come out exactly as recorded.",
            "- Without Baker: every table is JSON lines. Each audit-log entry's hash is the "
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
            "settings; Baker has not tested that across machines.",
            '- "Not found" never means "did not happen": an absence finding states what was '
            "searched and what the source could show.",
            "- The tamper check is as strong as its anchor: the last hash above, printed on the "
            "report. There is no signature or outside timestamp.",
            "",
        ]
    )
