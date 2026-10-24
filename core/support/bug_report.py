"""A bug report the examiner can send to the Mabillon team, holding no case data.

Built from an allowlist: every field is a version Mabillon ships, a yes or no, a count, a state
from a fixed set, a time, or a Mabillon source file and line. Nothing is copied from the case's
text or files. Left out on purpose:
- the case name, the expert's name, file names and folder paths (a path names the user);
- claim, record, document and quote text, and every error message (a message can quote any of
  those);
- hashes of inputs, records, the model file or the audit log, and the API key.

`check_clean` re-checks the finished text before anyone sees it: no long hex run (a SHA-256 or
a key), and none of the open case's name, file names, input hashes or folder. If it finds one,
the report is withheld rather than cleaned. Mabillon sends nothing itself: the examiner reads the
report on the Help page, saves it and attaches it to an email.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import sqlite3
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core import build as baker_build
from core import db
from core.audit import _local_model, quotes, rules
from core.audit._llm_json import PROMPTS_DIR, PromptMissingError, load_prompt, prompt_version
from core.casework import cases, protect
from core.casework.jobs import Job
from core.casework.model_check import GB, ModelCheck, total_memory
from core.contracts import CONTRACTS_VERSION
from core.llm import cloud as cloud_llm
from core.pipeline import PIPELINE_VERSION
from core.report.html import REPORT_VERSION
from core.review import audit_log
from core.support import errors
from core.support.contact import SUPPORT_EMAIL, SUPPORT_IS_PLACEHOLDER
from core.timeline import settings as timeline_settings

FORMAT = "baker-bug-report/1"
ROOT = Path(__file__).resolve().parents[2]
PROMPTS = {  # purpose in model_runs -> the prompt file Mabillon ships
    "stance": "stance.md",
    "review": "reviewer.md",
    "claims": "claims.md",
    "assumptions": "assumptions.md",
    "stance_cloud": "stance_cloud.md",  # an opted-in cloud stance run is stored as "stance"
}
# Case tables counted (row counts only). Names are fixed here, never read from the database.
COUNTED = (
    "sources",
    "devices",
    "accounts",
    "persons",
    "identity_links",
    "threads",
    "messages",
    "attachments",
    "calls",
    "contacts",
    "locations",
    "govdoc_paragraphs",
    "claims",
    "assumptions",
    "evidence_items",
    "evidence_reviews",
    "check_results",
    "stipulations",
    "verdicts",
    "pipeline_runs",
    "model_runs",
    "model_calls",
    "audit_log",
    "exhibits",
)
WITHHELD = (
    "case name, expert name, file names and folder paths",
    "claim, record, document and quote text",
    "error messages (only the error type and Mabillon's file and line are kept)",
    "hashes of inputs, records, the model file and the audit log; API keys",
)
_HEX_RUN = re.compile(r"[0-9a-fA-F]{32,}")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+()-]{0,63}")


class NotClean(RuntimeError):
    """The finished report holds something that looks like case data; it is withheld."""


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe(value: object) -> str | None:
    """A short name (a model or tool name) only when it is plain; otherwise left out."""
    s = str(value or "").strip()
    return s if _SAFE_NAME.fullmatch(s) and not _HEX_RUN.search(s) else None


# ---------------------------------------------------------------- sections


def _release() -> str | None:
    """The Mabillon release, read the way run records read it (source tree or installed package)."""
    got = baker_build.release()
    return None if got == baker_build.NOT_RECORDED else got


def _commit() -> str | None:
    """The commit Mabillon runs from, short form, from a checkout or the installer's BUILD_INFO.json
    (core/build.py). Short, so the report never holds a long hex run."""
    sha, _dirty = baker_build.commit()
    return sha[:12] if re.fullmatch(r"[0-9a-f]{7,40}", sha) else None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def shipped_prompts() -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for purpose, name in PROMPTS.items():
        try:
            out[purpose] = prompt_version(load_prompt(name, PROMPTS_DIR))
        except (PromptMissingError, OSError):
            out[purpose] = None
    return out


def baker_section() -> dict[str, Any]:
    return {
        "package": _release(),
        "commit": _commit(),
        "pipeline": PIPELINE_VERSION,
        "contracts": CONTRACTS_VERSION,
        "rules": rules.RULE_VERSION,
        "quote_check": quotes.VERSION,
        "report": REPORT_VERSION,
        "prompts": shipped_prompts(),
    }


def system_section() -> dict[str, Any]:
    mem = total_memory()
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "memory_gb": None if mem is None else round(mem / GB, 1),
        "packaged": bool(getattr(sys, "frozen", False)),
    }


def model_section(last_check: ModelCheck | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "runtime_installed": importlib.util.find_spec("llama_cpp") is not None,
        "runtime_version": _package_version("llama_cpp_python"),
        "config_found": False,
        "file_found": None,
        "file_gb": None,
        "name": None,
    }
    try:
        cfg = _local_model.load_config()
    except (_local_model.ModelConfigError, OSError):
        pass  # missing, invalid or unreadable: reported as no config found
    else:
        out["config_found"] = True
        out["name"] = _safe(cfg.name)
        try:
            out["file_found"] = cfg.path.is_file()
            if out["file_found"]:
                out["file_gb"] = round(cfg.path.stat().st_size / GB, 2)
        except OSError:  # unreadable or gone since the check: report it as not available
            out["file_found"] = False
            out["file_gb"] = None
    if last_check is None:
        out["last_check"] = None
    else:  # the result and how many lines of each level; the lines name paths and hashes
        levels = Counter(level for level, _ in last_check.lines)
        out["last_check"] = {
            "ok": last_check.ok,
            "at_utc": last_check.checked_at_utc or None,
            "lines": {k: levels.get(k, 0) for k in ("ok", "warn", "fail")},
        }
    return out


def cloud_section(key_ready: bool | None) -> dict[str, Any]:
    return {
        "key_set_up": key_ready,  # yes or no only, never the key
        "models_passed_stance_test": len(cloud_llm.PROBE_PASSED),
    }


# The MABILLON_* settings Mabillon reads, and their Baker-era BAKER_* names (core/paths.py). Any
# other name is left out: a name is user-chosen text and could carry a client, case or secret.
KNOWN_ENV = (
    "MABILLON_ANTHROPIC_API_KEY",
    "MABILLON_CASES",
    "MABILLON_CLOUD_CONFIG",
    "MABILLON_DEMO",
    "MABILLON_MIN_MEMORY_GB",
    "MABILLON_MODEL_CONFIG",
    "MABILLON_PINS",
    "BAKER_ANTHROPIC_API_KEY",
    "BAKER_CASES",
    "BAKER_CLOUD_CONFIG",
    "BAKER_DEMO",
    "BAKER_MIN_MEMORY_GB",
    "BAKER_MODEL_CONFIG",
    "BAKER_PINS",
)


def settings_section(many_cases: bool | None, case_count: int | None) -> dict[str, Any]:
    return {
        "screen_on_cases_folder": many_cases,
        "cases_in_folder": case_count,
        # names only: a value can be a path or a key
        "baker_env_set": sorted(k for k in KNOWN_ENV if k in os.environ),
    }


def job_section(job: Job | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {  # job.message is left out: it can quote an error about a named file
        "kind": job.kind,
        "state": job.state,
        "done": job.done,
        "total": job.total,
        "started_at_utc": _iso(job.started_at),
        "finished_at_utc": _iso(job.finished_at),
        "cloud": job.cloud,
    }


def _count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 - fixed names
    except db.Error:
        return None


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    try:
        return conn.execute(sql).fetchall()
    except db.Error:
        return []


def case_section(case: cases.Case, conn: sqlite3.Connection | None) -> dict[str, Any]:
    try:
        encryption = protect.state(case)
    except OSError:  # inputs unreadable: the report says so instead of failing
        encryption = "unavailable"
    out: dict[str, Any] = {"encryption": encryption}
    if conn is None:
        out["readable"] = False
        return out
    out["readable"] = True
    try:
        audit_log.require_intact(conn, audit_log.anchors_path(case.db))
        out["audit_log_intact"] = True
    except audit_log.ChainBroken:
        out["audit_log_intact"] = False
    except db.Error:
        out["audit_log_intact"] = None
    out["counts"] = {t: _count(conn, t) for t in COUNTED}
    out["sources"] = [
        {
            "kind": kind,
            "fidelity": fidelity,
            "extraction_type": extraction,
            "importer": _safe(importer),
            "importer_version": _safe(importer_version),
        }
        for kind, fidelity, extraction, importer, importer_version in _rows(
            conn,
            "SELECT s.kind, s.fidelity, s.extraction_type, c.importer, c.importer_version"
            " FROM sources s LEFT JOIN source_coverage c ON c.source_id = s.id ORDER BY s.rowid",
        )
    ]
    out["claims_by_status"] = dict(
        _rows(conn, "SELECT status, COUNT(*) FROM claims GROUP BY status ORDER BY status")
    )
    runs = []
    for status, started, finished, bv, cv, rv, cfg in _rows(
        conn,
        "SELECT status, started_at_utc, finished_at_utc, baker_version, contracts_version,"
        " rule_version, config_json FROM pipeline_runs ORDER BY started_at_utc DESC LIMIT 5",
    ):
        try:
            config = json.loads(cfg)
        except (TypeError, ValueError):
            config = {}
        config = config if isinstance(config, dict) else {}
        cloud = config.get("cloud")
        runs.append(
            {
                "status": status,
                "started_at_utc": started,
                "finished_at_utc": finished,
                "baker_version": _safe(bv),
                "contracts_version": _safe(cv),
                "rule_version": _safe(rv),
                "test_run": bool(config.get("fake")),
                "cloud": bool(cloud.get("use")) if isinstance(cloud, dict) else False,
            }
        )
    out["recent_runs"] = runs
    latest = _rows(conn, "SELECT id FROM pipeline_runs ORDER BY started_at_utc DESC LIMIT 1")
    verdicts: dict[str, int] = {}
    if latest:
        try:
            got = conn.execute(
                "SELECT verdict, supported_basis, COUNT(*) FROM verdicts"
                " WHERE pipeline_run_id = ? GROUP BY verdict, supported_basis",
                (latest[0][0],),
            ).fetchall()
        except db.Error:
            got = []  # a damaged or older case: report what else is readable
        for verdict, basis, n in got:
            verdicts[verdict if basis is None else f"{verdict}:{basis}"] = n
    out["latest_run_verdicts"] = verdicts
    shipped = shipped_prompts()
    model_runs: dict[str, dict[str, Any]] = {}
    for purpose, prompt, n in _rows(
        conn,
        "SELECT purpose, prompt_version, COUNT(*) FROM model_runs GROUP BY purpose, prompt_version",
    ):
        key = purpose if purpose in PROMPTS or _safe(purpose) else "other"
        row = model_runs.setdefault(key, {"runs": 0, "prompt_is_shipped_version": True})
        row["runs"] += n
        expected = {shipped.get(purpose)}
        if purpose == "stance":
            expected.add(shipped.get("stance_cloud"))
        if prompt not in expected - {None}:
            row["prompt_is_shipped_version"] = False
    out["model_runs"] = model_runs
    out["model_call_outcomes"] = dict(
        _rows(conn, "SELECT outcome, COUNT(*) FROM model_calls GROUP BY outcome ORDER BY outcome")
    )
    timeline = timeline_settings.from_case(case.settings)
    out["timeline_settings"] = {
        "tolerance_min": timeline.tolerance_min,
        "gap_hours": timeline.gap_hours,
    }
    return out


# ---------------------------------------------------------------- the report


def build(
    *,
    case: cases.Case | None = None,
    conn: sqlite3.Connection | None = None,
    job: Job | None = None,
    last_check: ModelCheck | None = None,
    cloud_key_ready: bool | None = None,
    many_cases: bool | None = None,
    case_count: int | None = None,
    recent_errors: Sequence[errors.ErrorEvent] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The bug report as a dict. `conn` is the open case's connection, or None."""
    return {
        "format": FORMAT,
        "made_at_utc": _iso(now or datetime.now(UTC)),
        "support": SUPPORT_EMAIL,
        "support_is_placeholder": SUPPORT_IS_PLACEHOLDER,
        "left_out": list(WITHHELD),
        "baker": baker_section(),
        "system": system_section(),
        "model": model_section(last_check),
        "cloud": cloud_section(cloud_key_ready),
        "settings": settings_section(many_cases, case_count),
        "last_job": job_section(job),
        "recent_errors": [
            e.record() for e in (errors.recent() if recent_errors is None else recent_errors)
        ],
        "open_case": None if case is None else case_section(case, conn),
    }


def sensitive_values(case: cases.Case | None, conn: sqlite3.Connection | None) -> set[str]:
    """Strings from the open case that must never appear in a report."""
    if case is None:
        return set()
    out = {case.name, str(case.folder), case.folder.name}
    if conn is not None:
        for name, sha in _rows(conn, "SELECT file_name, sha256 FROM sources"):
            out |= {str(name), str(sha), str(sha)[:16]}
    try:
        out |= {p.name for p in case.inputs.iterdir()}
    except OSError:
        pass
    # short names are left out of this check: "case" or "demo" would match the report's own
    # words. The report never copies them anyway; this is the second line of defence.
    return {s for s in out if len(s.strip()) >= 8}


def check_clean(text: str, sensitive: set[str]) -> None:
    if _HEX_RUN.search(text):
        raise NotClean("it contains a long hex value, which may be a hash or a key")
    # Only the values Mabillon filled in are checked, not the report's own keys: a case named
    # "Pipeline" must not match the "pipeline" key. Text that is not JSON is checked whole.
    try:
        lowered = "\n".join(_strings(json.loads(text))).lower()
    except ValueError:
        lowered = text.lower()
    for s in sensitive:
        if s.lower() in lowered:
            raise NotClean("it contains a name or value from the open case")


def _strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return [str(value)] if value is not None else []


def render(report: dict[str, Any], sensitive: set[str] | None = None) -> str:
    """The report as JSON text, checked clean. Raises NotClean instead of returning a leak."""
    text = json.dumps(report, indent=2, ensure_ascii=True, sort_keys=False) + "\n"
    check_clean(text, sensitive or set())
    return text
