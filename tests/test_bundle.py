"""The reproducibility bundle: export, offline verify, and tampering failing loudly. Synthetic
case01 only; case02 is the held-out case and is never used here."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit import rules
from core.audit import stance as stance_mod
from core.audit._local_model import RECEIVED_ACTION, SENT_ACTION, SentLog, raw_sha256
from core.bundle import export
from core.bundle.verify import FAIL, NOTE, PASS, failed, verify_bundle
from core.contracts import GoldClaim
from core.llm import cloud
from core.review import audit_log
from core.review.actions import ReviewError
from tests.test_cloud import FakeClient, FakeCloud, _Obj, _Quoter
from tests.test_report_consistency import START, _build

EXPERT = "expert:Dana Reyes"
AT = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _export(conn, tmp_path: Path, name: str = "bundle.zip") -> Path:  # noqa: ANN001
    return export.export_bundle(conn, tmp_path / name, EXPERT, clock=lambda: AT).path


def _levels(findings, check: str) -> set[str]:  # noqa: ANN001
    return {f.level for f in findings if f.check == check}


def _fails(findings) -> list[str]:  # noqa: ANN001
    return [f"{f.check}: {f.detail}" for f in findings if f.level == FAIL]


@pytest.fixture(scope="module")
def reviewed(tmp_path_factory):  # noqa: ANN201
    """case01 audited, AI-reviewed, expert-reviewed, re-decided, a verdict confirmed and one
    overridden, a stipulation and an account link added after (tests/test_report_consistency.py)."""
    folder = tmp_path_factory.mktemp("bundle-reviewed")
    conn = _build(folder / "case01.db", START)
    path = _export(conn, folder)
    yield conn, path
    conn.close()


@pytest.fixture(scope="module")
def hosted(tmp_path_factory):  # noqa: ANN201
    """Three case01 claims labelled through the cloud path (a stand-in API), every request and
    answer logged."""
    from core import pipeline
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl

    folder = tmp_path_factory.mktemp("bundle-hosted")
    conn = rp.build_case("case01", folder / "case01.db")
    gold = load_jsonl(rp.gold_path("case01"), GoldClaim)
    up = _Quoter(FakeCloud([]))
    up.why = "the record names the account"
    comps = rp.model_free_components(conn, rp.assumption_sheet("case01"), gold)
    comps.labeler = stance_mod.create(conn, cloud_model=up)
    comps.model_runs = (
        *[m for m in comps.model_runs if m.purpose != "stance"],
        *comps.labeler.model_runs,
    )
    pipeline.run_audit(conn, comps, claim_ids=[g.claim_id for g in gold][:3])
    path = _export(conn, folder)
    yield conn, path
    conn.close()


def _rewrite(src: Path, dst: Path, name: str, edit: Callable[[str], str], rehash: bool = True):
    """A copy of the bundle with one file edited; with rehash, bundle.json's hash for it is
    updated too, as a careful tamperer would."""
    with zipfile.ZipFile(src) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    files[name] = edit(files[name].decode("utf-8")).encode("utf-8")
    if rehash:
        manifest = json.loads(files[export.MANIFEST])
        manifest["files"][name]["sha256"] = hashlib.sha256(files[name]).hexdigest()
        files[export.MANIFEST] = json.dumps(manifest).encode()
    with zipfile.ZipFile(dst, "w") as zf:
        for n, data in files.items():
            zf.writestr(n, data)
    return dst


def _edit_row(table: str, match: Callable[[dict], bool], change: Callable[[dict], None]):
    def edit(text: str) -> str:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            row = json.loads(line)
            if match(row):
                change(row)
                lines[i] = json.dumps(row, ensure_ascii=False, sort_keys=True)
                return "\n".join(lines) + "\n"
        raise AssertionError(f"no matching row in {table}")

    return f"{export.TABLES}{table}.jsonl", edit


# ---------------------------------------------------------------- export, then verify


def test_a_reviewed_case_verifies_offline_and_every_verdict_re_derives(reviewed):
    _conn, path = reviewed
    findings = verify_bundle(path)
    assert not failed(findings), _fails(findings)
    for check in ("files", "versions", "tables", "audit log", "inputs", "labels", "verdicts",
                  "report"):  # fmt: skip
        assert PASS in _levels(findings, check), check
    verdicts = next(f for f in findings if f.check == "verdicts" and f.level == PASS)
    assert "20 verdicts" in verdicts.detail and "set by the expert" in verdicts.detail


def test_a_hosted_case_binds_every_answer_to_the_log_and_says_it_cannot_be_regenerated(hosted):
    conn, path = hosted
    findings = verify_bundle(path)
    assert not failed(findings), _fails(findings)
    assert PASS in _levels(findings, "model calls") and PASS in _levels(findings, "labels")
    sent = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?", (SENT_ACTION,))
    received = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?", (RECEIVED_ACTION,))
    assert sent.fetchone()[0] == received.fetchone()[0] > 0
    with zipfile.ZipFile(path) as zf:
        note = zf.read(export.METHOD).decode()
        manifest = json.loads(zf.read(export.MANIFEST))
    assert "Labels from a hosted model (Anthropic, claude-opus-5-5)" in note
    assert "cannot be regenerated exactly" in note
    (stance_run,) = [m for m in manifest["models"] if m["purpose"] == "stance"]
    assert stance_run["where"] == "cloud" and stance_run["effort"] == "medium"


def test_the_bundle_holds_every_table_the_report_and_the_export_entry(reviewed):
    conn, path = reviewed
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read(export.MANIFEST))
    assert {f"{export.TABLES}{t}.jsonl" for t, _ in export.schema_tables()} <= names
    assert {export.MANIFEST, export.METHOD, export.REPORT} <= names
    last = conn.execute("SELECT actor, action, hash FROM audit_log ORDER BY seq DESC LIMIT 1")
    actor, action, h = last.fetchone()
    assert (actor, action) == (EXPERT, export.EXPORT_ACTION)
    assert manifest["audit_log"]["last_hash"] == h
    assert manifest["run"]["rule_version"] == rules.RULE_VERSION
    assert manifest["notice"] == export.NOTICE and "counsel" in export.NOTICE


def test_export_is_never_silent_or_partial(reviewed, tmp_path):
    conn, path = reviewed
    with pytest.raises(ReviewError, match="already exists"):
        export.export_bundle(conn, path, EXPERT)
    with pytest.raises(ReviewError):
        export.export_bundle(conn, tmp_path / "x.zip", "system")  # an expert's act only


def test_an_unfinished_audit_cannot_be_exported(tmp_path):
    from core import pipeline
    from eval import run_pipeline as rp

    conn = rp.build_case("case01", tmp_path / "case01.db")
    with pytest.raises(ReviewError, match="no completed audit"):
        export.export_bundle(conn, tmp_path / "b.zip", EXPERT)
    conn.execute(
        "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version, contracts_version,"
        " rule_version, config_json) VALUES ('run:x', ?, 'running', '0', '0', '0', '{}')",
        (pipeline.iso(AT),),
    )
    with pytest.raises(ReviewError):
        export.export_bundle(conn, tmp_path / "b.zip", EXPERT)


# ---------------------------------------------------------------- tampering fails loudly


def test_an_edited_file_fails_its_hash(reviewed, tmp_path):
    _conn, path = reviewed
    bad = _rewrite(path, tmp_path / "b.zip", export.METHOD, lambda t: t + "x", rehash=False)
    assert _levels(verify_bundle(bad), "files") == {FAIL}


def test_an_added_file_fails(reviewed, tmp_path):
    _conn, path = reviewed
    bad = tmp_path / "b.zip"
    bad.write_bytes(path.read_bytes())
    with zipfile.ZipFile(bad, "a") as zf:
        zf.writestr("extra.txt", "x")
    assert _levels(verify_bundle(bad), "files") == {FAIL}


def test_an_altered_label_fails(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "evidence_items",
        lambda r: r["stance"] == "supports",
        lambda r: r.update(stance="contradicts"),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "labels")


def test_an_altered_hosted_answer_fails(hosted, tmp_path):
    _conn, path = hosted
    name, edit = _edit_row(
        "model_calls",
        lambda r: r["outcome"] == "ok",
        lambda r: r.update(raw_output=r["raw_output"].replace("supports", "contradicts")),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "model calls")


def test_an_altered_expert_decision_fails(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "evidence_reviews",
        lambda r: r["reviewer_kind"] == "expert" and r["status"] == "dismissed",
        lambda r: r.update(status="accepted"),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "audit log")


def test_an_altered_input_hash_fails(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "sources", lambda r: r["kind"] != "govdoc", lambda r: r.update(sha256="0" * 64)
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "inputs")


def test_an_altered_verdict_fails(reviewed, tmp_path):
    _conn, path = reviewed
    with zipfile.ZipFile(path) as zf:
        run_id = json.loads(zf.read(export.MANIFEST))["run"]["run_id"]
    name, edit = _edit_row(
        "verdicts",
        lambda r: r["pipeline_run_id"] == run_id and r["verdict"] == "unproven",
        lambda r: r.update(verdict="contradicted"),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "verdicts")


def test_an_altered_log_entry_fails_the_chain(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "audit_log",
        lambda r: r["action"] == "verdict.override",
        lambda r: r.update(payload_json=r["payload_json"].replace("contradicted", "supported")),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "audit log")


def test_a_report_that_is_not_the_one_the_tables_render_fails(reviewed, tmp_path):
    _conn, path = reviewed
    edit = lambda t: t.replace("Baker claims report</h1>", "Baker report</h1>")  # noqa: E731
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", export.REPORT, edit))
    assert _levels(findings, "report") == {FAIL}


def test_other_rules_name_the_commit_to_verify_with(reviewed, monkeypatch):
    _conn, path = reviewed
    monkeypatch.setattr(rules, "RULE_VERSION", "9.9.9")
    findings = verify_bundle(path)
    (f,) = [f for f in findings if f.check == "versions"]
    assert f.level == FAIL and "commit" in f.detail


def test_original_files_are_compared_by_hash(reviewed, tmp_path):
    conn, path = reviewed
    name, sha = conn.execute("SELECT file_name, sha256 FROM sources LIMIT 1").fetchone()
    folder = tmp_path / "inputs"
    folder.mkdir()
    (folder / name).write_text("not the original")
    findings = verify_bundle(path, folder)
    assert any(f.level == FAIL and name in f.detail for f in findings)
    (folder / name).unlink()
    assert any(f.level == NOTE and name in f.detail for f in verify_bundle(path, folder))
    assert sha  # the recorded hash is what an original file is checked against


def test_a_bundle_that_is_not_a_zip_fails(tmp_path):
    p = tmp_path / "b.zip"
    p.write_text("no")
    assert failed(verify_bundle(p))


# ---------------------------------------------------------------- the cloud answer's identity


def test_each_cloud_answer_is_logged_with_the_api_ids_and_raw_hash(tmp_path):
    from core.db import apply_schema, connect

    conn = connect(tmp_path / "c.db")
    apply_schema(conn)
    text = '{"stance": "irrelevant", "quote": "", "rationale": "No."}'
    resp = _Obj(
        id="msg_01",
        _request_id="req_01",
        model="claude-opus-5-5",
        stop_reason="end_turn",
        content=[_Obj(type="text", text=text)],
        usage=_Obj(input_tokens=10, output_tokens=5),
    )
    model = cloud.ClaudeModel(cloud.CloudConfig(api_key="sk-ant-x"), client=FakeClient(resp))
    out = SentLog(model, conn).generate_json("p", {"type": "object"})
    assert (out.message_id, out.request_id, out.served_model) == ("msg_01", "req_01", model.name)
    rows = conn.execute("SELECT action, payload_json FROM audit_log ORDER BY seq").fetchall()
    assert [a for a, _ in rows] == [SENT_ACTION, RECEIVED_ACTION]
    sent, got = (json.loads(p) for _, p in rows)
    assert got["request_sha256"] == sent["request_sha256"]
    assert (got["message_id"], got["request_id"], got["model"]) == ("msg_01", "req_01", model.name)
    assert got["raw_sha256"] == raw_sha256(text)
    assert audit_log.verify_chain(conn)
