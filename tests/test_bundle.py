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


def _export(conn, tmp_path: Path, name: str = "bundle.zip", include: str | None = "all") -> Path:  # noqa: ANN001
    """The whole case by default: the tampering tests below change rows a scoped bundle may
    leave out. Scoped bundles have their own tests (pass include=None)."""
    return export.export_bundle(
        conn, tmp_path / name, EXPERT, counsel_confirmed=True, clock=lambda: AT, include=include
    ).path


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


def test_the_export_is_logged_after_the_file_with_its_hash(reviewed):
    conn, path = reviewed
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read(export.MANIFEST))
    assert {f"{export.TABLES}{t}.jsonl" for t, _ in export.schema_tables()} <= names
    assert {export.MANIFEST, export.METHOD, export.REPORT} <= names
    entries = conn.execute(
        "SELECT seq, actor, payload_json, prev_hash FROM audit_log WHERE action = ?",
        (export.EXPORT_ACTION,),
    ).fetchall()
    # the fixture's own export: other tests in this module export the same case again
    seq, actor, payload, prev = next(e for e in entries if path.name in e[2])
    logged = json.loads(payload)
    assert actor == EXPERT and logged["counsel_confirmed"] is True
    assert logged["bundle_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    # the bundle holds the log as it stood just before its own export entry
    assert manifest["audit_log"]["last_hash"] == prev == logged["audit_log_head"]["hash"]
    assert manifest["audit_log"]["last_seq"] == seq - 1
    assert manifest["contents"] == logged["contents"] and manifest["counsel_confirmed"] is True
    assert manifest["run"]["rule_version"] == rules.RULE_VERSION
    assert manifest["notice"] == export.NOTICE and "counsel" in export.NOTICE


def test_export_is_never_silent_or_partial(reviewed, tmp_path):
    conn, path = reviewed
    with pytest.raises(ReviewError, match="already exists"):
        export.export_bundle(conn, path, EXPERT, counsel_confirmed=True)
    with pytest.raises(ReviewError):  # an expert's act only
        export.export_bundle(conn, tmp_path / "x.zip", "system", counsel_confirmed=True)


def test_nothing_is_exported_without_the_counsel_confirmation(reviewed, tmp_path):
    conn, _path = reviewed
    before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    with pytest.raises(ReviewError, match="counsel"):
        export.export_bundle(conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=False)
    assert not (tmp_path / "x.zip").exists()
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before
    text = export.describe(export.contents(conn))
    assert "dismissed ones too" in text and "every prompt" in text and "evidence_items" in text


def test_the_cli_writes_nothing_without_the_confirmation(reviewed, tmp_path, capsys):
    from cli.main import main

    conn, _path = reviewed
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    assert main(["export-bundle", "--db", str(db), "--out", str(tmp_path / "x.zip"),
                 "--by", EXPERT]) == 2  # fmt: skip
    assert not (tmp_path / "x.zip").exists()
    assert "--confirm-counsel-reviewed" in capsys.readouterr().err


def test_an_encrypted_case_never_exports_in_plain_form(reviewed, tmp_path):
    from core import encryption
    from core.bundle import sealed

    conn, _path = reviewed
    with pytest.raises(ReviewError, match="encrypted"):
        export.export_bundle(
            conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=True, encrypted_case=True
        )
    assert not (tmp_path / "x.zip").exists()
    r = export.export_bundle(
        conn,
        tmp_path / "s.zip",
        EXPERT,
        counsel_confirmed=True,
        encrypted_case=True,
        passphrase="correct horse battery",
    )
    blob = r.path.read_bytes()
    assert sealed.is_sealed(blob) and b"tables/" not in blob and r.encrypted
    assert not zipfile.is_zipfile(r.path)
    assert _levels(verify_bundle(r.path), "files") == {FAIL}  # no passphrase
    assert _levels(verify_bundle(r.path, passphrase="wrong passphrase!"), "files") == {FAIL}
    findings = verify_bundle(r.path, passphrase="correct horse battery")
    assert not failed(findings), _fails(findings)
    with pytest.raises(encryption.WrongSecret):
        sealed.open_sealed(blob[:-1] + bytes([blob[-1] ^ 1]), "correct horse battery")


def test_a_failed_write_leaves_no_bundle_and_no_success_entry(reviewed, tmp_path, monkeypatch):
    conn, _path = reviewed
    before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    def full_disk(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(export.os, "fsync", full_disk)
    with pytest.raises(OSError):
        export.export_bundle(conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=True)
    assert not list(tmp_path.iterdir())  # neither the bundle nor a partial file
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before


def test_a_bundle_the_log_cannot_record_is_removed(reviewed, tmp_path, monkeypatch):
    conn, _path = reviewed

    def refuse(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("log unwritable")

    monkeypatch.setattr(export.audit_log, "append", refuse)
    with pytest.raises(RuntimeError):
        export.export_bundle(conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=True)
    assert not list(tmp_path.iterdir())


def test_partial_coverage_never_reads_as_fully_verified(reviewed):
    from core.bundle.verify import outcome

    _conn, path = reviewed
    findings = verify_bundle(path)  # stand-in labels, no original files given
    code, line = outcome(findings)
    assert code == 2 and "partly verified" in line and "every check ran" not in line
    assert outcome([f for f in findings if f.level == PASS]) == (
        0,
        "bundle verified: every check ran and passed",
    )
    assert outcome([*findings, type(findings[0])(FAIL, "x", "y")])[0] == 1


def test_an_unfinished_audit_cannot_be_exported(tmp_path):
    from core import pipeline
    from eval import run_pipeline as rp

    conn = rp.build_case("case01", tmp_path / "case01.db")
    with pytest.raises(ReviewError, match="no completed audit"):
        export.export_bundle(conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True)
    conn.execute(
        "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version, contracts_version,"
        " rule_version, config_json) VALUES ('run:x', ?, 'running', '0', '0', '0', '{}')",
        (pipeline.iso(AT),),
    )
    with pytest.raises(ReviewError):
        export.export_bundle(conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True)


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


def _case(tmp_path: Path):  # noqa: ANN202
    from core.db import apply_schema, connect

    conn = connect(tmp_path / "c.db")
    apply_schema(conn)
    return conn


def _logged(conn, action: str) -> list[dict]:  # noqa: ANN001
    rows = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq", (action,)
    )
    return [json.loads(p) for (p,) in rows]


def test_an_answer_that_cannot_be_logged_is_not_used_and_the_audit_pauses(tmp_path):
    from core.audit._llm_json import CloudPaused

    conn = _case(tmp_path)

    class Answers(FakeCloud):
        def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
            out = super().generate_json(prompt, schema, params)
            conn.execute("BEGIN")  # an open write transaction: the answer cannot be logged
            return out

    up = Answers(['{"stance": "irrelevant", "quote": "", "rationale": "No."}'])
    with pytest.raises(CloudPaused, match="not used"):
        SentLog(up, conn).generate_json("p", {"type": "object"})
    conn.rollback()
    assert len(_logged(conn, SENT_ACTION)) == 1 and not _logged(conn, RECEIVED_ACTION)
    assert not conn.execute("SELECT 1 FROM model_calls").fetchone()  # nothing stored


def test_a_retried_send_logs_one_answer_for_the_attempt_that_succeeded(tmp_path):
    conn = _case(tmp_path)
    text = '{"stance": "irrelevant", "quote": "", "rationale": "No."}'
    down = cloud.CloudError("APIConnectionError: reset", sticky=True, retryable=True)
    up = FakeCloud([down, text])
    assert SentLog(up, conn, sleep=lambda s: None).generate_json("p", {}).raw_text == text
    sent, got = _logged(conn, SENT_ACTION), _logged(conn, RECEIVED_ACTION)
    assert [s["attempt"] for s in sent] == [1, 2]
    assert len(got) == 1 and got[0]["attempt"] == 2
    assert got[0]["request_sha256"] == sent[1]["request_sha256"]
    assert got[0]["raw_sha256"] == raw_sha256(text)


# ---------------------------------------------------------------- every row is bound to the log


def _manifest_edit(change: Callable[[dict], None]) -> Callable[[str], str]:
    def edit(text: str) -> str:
        manifest = json.loads(text)
        change(manifest)
        return json.dumps(manifest)

    return edit


def _rehashed(src: Path, dst: Path, edits: dict[str, Callable[[str], str]]) -> Path:
    """Several files edited, bundle.json's hashes updated for each."""
    for name, edit in edits.items():
        _rewrite(src, dst, name, edit)
        src = dst
    return dst


def test_model_identities_in_bundle_json_must_match_the_tables(hosted, tmp_path):
    _conn, path = hosted

    def change(m: dict) -> None:
        for model in m["models"]:
            model["model_name"] = "some-other-model"

    bad = _rewrite(path, tmp_path / "b.zip", export.MANIFEST, _manifest_edit(change), False)
    assert FAIL in _levels(verify_bundle(bad), "bundle.json")


def test_an_edited_method_note_fails_even_when_rehashed(reviewed, tmp_path):
    _conn, path = reviewed
    edit = lambda t: t.replace("## Limits", "## Limits\n\n- None.")  # noqa: E731
    bad = _rewrite(path, tmp_path / "b.zip", export.METHOD, edit)
    assert FAIL in _levels(verify_bundle(bad), "bundle.json")


@pytest.mark.parametrize(
    ("table", "match", "change"),
    [
        ("check_results", lambda r: True, lambda r: r.update(detail=r["detail"] + " (edited)")),
        ("check_results", lambda r: r["outcome"] != "fail", lambda r: r.update(outcome="fail")),
        ("assumptions", lambda r: True, lambda r: r.update(text=r["text"] + " (edited)")),
        ("assumptions", lambda r: r["is_core"] == 1, lambda r: r.update(is_core=0)),
        ("evidence_items", lambda r: True, lambda r: r.update(locator="elsewhere")),
        ("evidence_items", lambda r: True, lambda r: r.update(rationale="Made up.")),
    ],
)
def test_a_row_a_verdict_rests_on_cannot_be_edited(reviewed, tmp_path, table, match, change):
    _conn, path = reviewed
    name, edit = _edit_row(table, match, change)
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "rows"), _fails(findings)


def test_a_hosted_label_cannot_lose_its_model_run(hosted, tmp_path):
    _conn, path = hosted
    name, edit = _edit_row(
        "evidence_items",
        lambda r: r["model_run_id"] is not None,
        lambda r: r.update(model_run_id=None, rationale="Made up."),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "rows")


def test_an_item_naming_no_model_run_is_a_stand_in_only_in_a_test_run(hosted):
    from core.bundle.verify import _stand_in

    conn, _path = hosted
    assert _stand_in(conn, None, test_run=True)
    assert not _stand_in(conn, None, test_run=False)


def test_an_evidence_item_must_cite_its_records_own_source(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row("evidence_items", lambda r: True, lambda r: r.update(locator="x!1"))
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "labels")


def test_an_ai_review_cannot_be_reworded(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "evidence_reviews",
        lambda r: r["reviewer_kind"] == "ai",
        lambda r: r.update(reason="The reviewer said something else."),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "rows")


def test_a_model_calls_subject_or_run_cannot_be_reattributed(hosted, tmp_path):
    _conn, path = hosted
    name, edit = _edit_row(
        "model_calls",
        lambda r: r["outcome"] == "ok",
        lambda r: r.update(subject_json='["asm:x","msg:y"]'),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "model calls")


def test_a_stipulation_must_say_what_the_expert_confirmed(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "stipulations",
        lambda r: r["status"] == "confirmed",
        lambda r: r.update(statement="Someone else used the phone."),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "stipulations")


def test_a_rewritten_rationale_must_match_exactly():
    from types import SimpleNamespace

    from core.bundle.verify import _same_label
    from core.ingest import forwarded

    answer = SimpleNamespace(stance="contradicts", quote="q", rationale="Sent at 9.")

    def item(stance: str, rationale: str) -> tuple:
        return ("ev", "a", "r", stance, "q", rationale, "m", "s", "l")

    assert _same_label(item("contradicts", "Sent at 9."), answer)
    assert _same_label(item("complicates", stance_mod.NOT_THE_MESSAGE + "Sent at 9."), answer)
    note = f"{forwarded.STANCE_NOTE}contradicts. Sent at 9."
    assert _same_label(item("complicates", note), answer)
    assert not _same_label(
        item("complicates", stance_mod.NOT_THE_MESSAGE + "Invented. Sent at 9."), answer
    )
    assert not _same_label(item("complicates", "Invented. " + note), answer)


# ------------------------------------------------------------ malformed bundles fail, not crash


def test_a_malformed_files_list_fails_without_a_crash(reviewed, tmp_path):
    _conn, path = reviewed
    edit = _manifest_edit(lambda m: m.update(files=[]))
    bad = _rewrite(path, tmp_path / "b.zip", export.MANIFEST, edit, rehash=False)
    assert _levels(verify_bundle(bad), "files") == {FAIL}


def test_an_unreadable_log_payload_fails_without_a_crash(reviewed, tmp_path):
    _conn, path = reviewed
    name, edit = _edit_row(
        "audit_log", lambda r: r["action"] == "import", lambda r: r.update(payload_json="{")
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "audit log")
    assert not _levels(findings, "inputs")  # nothing ran on a log that failed


def test_an_inputs_folder_that_does_not_exist_fails(reviewed, tmp_path):
    _conn, path = reviewed
    findings = verify_bundle(path, tmp_path / "no-such-folder")
    assert FAIL in _levels(findings, "inputs")


# ---------------------------------------------------------------- export preconditions


def test_no_export_while_a_newer_audit_has_not_finished(reviewed, tmp_path):
    from core import pipeline

    conn, _path = reviewed
    with conn:
        conn.execute(
            "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version,"
            " contracts_version, rule_version, config_json)"
            " VALUES ('run:newer', '2999-01-01T00:00:00Z', 'running', '0', '0', '0', '{}')"
        )
    try:
        assert pipeline.latest_attempt(conn) is not None
        with pytest.raises(ReviewError, match="newer audit"):
            export.export_bundle(conn, tmp_path / "b.zip", EXPERT, counsel_confirmed=True)
        assert not (tmp_path / "b.zip").exists()
    finally:
        with conn:
            conn.execute("DELETE FROM pipeline_runs WHERE id = 'run:newer'")


def test_an_encrypted_cases_copies_are_hashed_through_decryption(tmp_path, monkeypatch):
    from core import encryption

    folder = tmp_path / "inputs"
    folder.mkdir()
    (folder / "a.bin").write_bytes(b"ciphertext")
    items = [{"sha256": "plain-sha"}, {"sha256": "other"}]
    monkeypatch.setattr(export.encryption, "plain_sha256", lambda p: "plain-sha")
    export._case_copies(items, folder)
    assert [i["case_copy_matches_at_export"] for i in items] == [True, False]

    def locked(p):  # noqa: ANN001, ANN202
        raise encryption.CaseLocked("locked")

    monkeypatch.setattr(export.encryption, "plain_sha256", locked)
    export._case_copies(items, folder)
    assert [i["case_copy_matches_at_export"] for i in items] == [None, None]


def test_a_refused_cloud_answer_is_logged_with_its_ids(tmp_path):
    conn = _case(tmp_path)
    resp = _Obj(
        id="msg_02",
        _request_id="req_02",
        model="claude-opus-5-5",
        stop_reason="refusal",
        content=[_Obj(type="text", text="I can't help with that.")],
        usage=_Obj(input_tokens=10, output_tokens=5),
    )
    model = cloud.ClaudeModel(cloud.CloudConfig(api_key="sk-ant-x"), client=FakeClient(resp))
    with pytest.raises(cloud.CloudError, match="declined"):
        SentLog(model, conn).generate_json("p", {"type": "object"})
    (got,) = _logged(conn, RECEIVED_ACTION)
    assert (got["message_id"], got["request_id"], got["stop_reason"]) == (
        "msg_02",
        "req_02",
        "refusal",
    )
    assert got["refused"] == "the cloud model declined to answer"
    assert got["raw_sha256"] == raw_sha256("I can't help with that.")


# ---------------------------------------------------------------- claims, expert reviews, settings


def test_an_audited_claim_cannot_be_reworded_or_hidden(reviewed, tmp_path):
    _conn, path = reviewed
    for change in (
        lambda r: r.update(text="The defendant ran the group."),
        lambda r: r.update(status="removed"),
    ):
        name, edit = _edit_row("claims", lambda r: r["status"] != "removed", change)
        findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
        assert FAIL in _levels(findings, "claims"), _fails(findings)


def test_a_claim_the_expert_changed_after_the_audit_still_verifies(tmp_path):
    from core.contracts import ClaimStatus
    from core.review.actions import set_claim_status

    conn = _build(tmp_path / "case01.db", START)
    claim_id = conn.execute("SELECT id FROM claims WHERE status = 'accepted' LIMIT 1").fetchone()
    set_claim_status(conn, claim_id[0], ClaimStatus.ACCEPTED, EXPERT, clock=lambda: AT)
    findings = verify_bundle(_export(conn, tmp_path))
    assert PASS in _levels(findings, "claims") and not failed(findings), _fails(findings)
    conn.close()


def test_an_expert_decision_cannot_be_moved_to_other_evidence(reviewed, tmp_path):
    conn, path = reviewed
    rid, eid, seq = conn.execute(
        "SELECT id, evidence_id, seq FROM evidence_reviews WHERE reviewer_kind = 'expert' LIMIT 1"
    ).fetchone()
    other = conn.execute(
        "SELECT e.id FROM evidence_items e WHERE e.id != ? AND NOT EXISTS"
        " (SELECT 1 FROM evidence_reviews r WHERE r.evidence_id = e.id AND r.seq = ?) LIMIT 1",
        (eid, seq),
    ).fetchone()[0]
    name, edit = _edit_row(
        "evidence_reviews", lambda r: r["id"] == rid, lambda r: r.update(evidence_id=other)
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "expert reviews"), _fails(findings)


def test_the_timeline_settings_are_the_logged_ones(reviewed, tmp_path):
    conn, path = reviewed
    edit = _manifest_edit(lambda m: m["timeline_settings"].update(gap_hours=1))
    bad = _rewrite(path, tmp_path / "b.zip", export.MANIFEST, edit, rehash=False)
    assert FAIL in _levels(verify_bundle(bad), "bundle.json")
    from core.timeline.settings import Settings

    with pytest.raises(ReviewError, match="timeline settings"):
        export.export_bundle(
            conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=True, timeline=Settings(5, 1)
        )


def test_a_bundle_without_its_method_note_fails_without_a_crash(reviewed, tmp_path):
    _conn, path = reviewed
    with zipfile.ZipFile(path) as zf:
        files = {n: zf.read(n) for n in zf.namelist() if n != export.METHOD}
    manifest = json.loads(files[export.MANIFEST])
    del manifest["files"][export.METHOD]
    files[export.MANIFEST] = json.dumps(manifest).encode()
    bad = tmp_path / "b.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        for n, data in files.items():
            zf.writestr(n, data)
    assert _levels(verify_bundle(bad), "files") == {FAIL}


# ---------------------------------------------------------------- Codex round 3 on #104


def test_a_model_run_cannot_be_reattributed(hosted, tmp_path):
    _conn, path = hosted
    name, edit = _edit_row(
        "model_runs", lambda r: r["purpose"] == "stance", lambda r: r.update(model_name="other")
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "rows"), _fails(findings)


def test_a_cited_records_metadata_cannot_be_edited(reviewed, tmp_path):
    conn, path = reviewed
    rid = conn.execute(
        "SELECT record_id FROM evidence_items WHERE record_id IN (SELECT id FROM messages) LIMIT 1"
    ).fetchone()[0]
    for change in (
        lambda r: r.update(ts_raw="01/01/2020 00:00"),
        lambda r: r.update(direction="unknown" if r["direction"] != "unknown" else "incoming"),
        lambda r: r.update(body=r["body"] + " and more"),
    ):
        name, edit = _edit_row("messages", lambda r: r["id"] == rid, change)
        findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
        assert FAIL in _levels(findings, "rows"), _fails(findings)


def test_the_runs_versions_and_settings_are_bound_to_the_log(reviewed, tmp_path):
    conn, path = reviewed
    run_id = json.loads(zipfile.ZipFile(path).read(export.MANIFEST))["run"]["run_id"]
    for change in (
        lambda r: r.update(config_json=r["config_json"].replace("{", '{"extra":1,', 1)),
        lambda r: r.update(finished_at_utc="2026-01-01T00:00:00Z"),
    ):
        name, edit = _edit_row("pipeline_runs", lambda r: r["id"] == run_id, change)
        findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
        assert FAIL in _levels(findings, "run"), _fails(findings)


def test_a_verdicts_time_is_bound_to_the_log(reviewed, tmp_path):
    _conn, path = reviewed
    run_id = json.loads(zipfile.ZipFile(path).read(export.MANIFEST))["run"]["run_id"]
    name, edit = _edit_row(
        "verdicts",
        lambda r: r["pipeline_run_id"] == run_id,
        lambda r: r.update(decided_at_utc="2026-01-01T00:00:00Z"),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "verdicts"), _fails(findings)


def test_identity_links_are_what_the_logged_actions_left(reviewed, tmp_path):
    _conn, path = reviewed
    assert PASS in _levels(verify_bundle(path), "identity links")
    for change in (
        lambda r: r.update(status="rejected", tier="inferred"),
        lambda r: r.update(decided_by="expert:Someone Else"),
        lambda r: r.update(decided_at_utc="2026-01-01T00:00:00Z"),
    ):
        name, edit = _edit_row("identity_links", lambda r: r["status"] == "confirmed", change)
        findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
        assert FAIL in _levels(findings, "identity links"), _fails(findings)
    gone = _rewrite(
        path,
        tmp_path / "b.zip",
        f"{export.TABLES}identity_links.jsonl",
        lambda t: "".join(x + "\n" for x in t.splitlines() if '"confirmed"' not in x),
    )
    assert FAIL in _levels(verify_bundle(gone), "identity links")


def test_a_claim_edited_after_the_audit_keeps_its_other_fields_bound(tmp_path):
    from core.contracts import ClaimStatus
    from core.review.actions import set_claim_status

    conn = _build(tmp_path / "case01.db", START)
    claim_id = conn.execute("SELECT id FROM claims WHERE status = 'accepted' LIMIT 1").fetchone()[0]
    set_claim_status(conn, claim_id, ClaimStatus.EDITED, EXPERT, "Reworded.", clock=lambda: AT)
    path = _export(conn, tmp_path)
    findings = verify_bundle(path)
    assert PASS in _levels(findings, "claims") and NOTE not in _levels(findings, "claims")
    name, edit = _edit_row(
        "claims",
        lambda r: r["id"] == claim_id,
        lambda r: r.update(claim_type="role" if r["claim_type"] != "role" else "count"),
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "claims"), _fails(findings)
    conn.close()


def test_a_listed_file_outside_the_format_fails(reviewed, tmp_path):
    _conn, path = reviewed
    with zipfile.ZipFile(path) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    files["extra.txt"] = b"x"
    manifest = json.loads(files[export.MANIFEST])
    manifest["files"]["extra.txt"] = {"sha256": hashlib.sha256(b"x").hexdigest(), "bytes": 1}
    files[export.MANIFEST] = json.dumps(manifest).encode()
    bad = tmp_path / "b.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        for n, data in files.items():
            zf.writestr(n, data)
    assert FAIL in _levels(verify_bundle(bad), "files")


def test_a_sealed_header_with_other_kdf_settings_fails_cleanly(reviewed, tmp_path):
    from core import encryption
    from core.bundle import sealed

    _conn, path = reviewed
    blob = sealed.seal(path.read_bytes(), "a long bundle passphrase")
    rest = blob[len(sealed.MAGIC) :]
    n = int.from_bytes(rest[:4], "big")
    for kdf in ({"name": "scrypt", "n": 0, "r": 8, "p": 1}, {"name": "scrypt", "n": 1 << 30}):
        header = json.loads(rest[4 : 4 + n])
        header["kdf"] = kdf
        h = json.dumps(header, sort_keys=True).encode()
        bad = sealed.MAGIC + len(h).to_bytes(4, "big") + h + rest[4 + n :]
        with pytest.raises(encryption.EncryptionError):
            sealed.open_sealed(bad, "a long bundle passphrase")
        (tmp_path / "b.zip").write_bytes(bad)
        found = verify_bundle(tmp_path / "b.zip", passphrase="a long bundle passphrase")
        assert _levels(found, "files") == {FAIL}


def test_a_hosted_answer_no_digest_names_is_noted_not_failed(hosted, tmp_path):
    _conn, path = hosted

    def add_legacy(text: str) -> str:
        rows = [json.loads(x) for x in text.splitlines()]
        old = dict(next(r for r in rows if r["raw_output"]))
        old.update(id=old["id"] + "-legacy", seq=10_000, raw_output=old["raw_output"] + " ")
        return text + json.dumps(old, sort_keys=True) + "\n"

    bad = _rewrite(path, tmp_path / "b.zip", f"{export.TABLES}model_calls.jsonl", add_legacy)
    findings = verify_bundle(bad)
    assert FAIL not in _levels(findings, "model calls"), _fails(findings)
    assert NOTE in _levels(findings, "model calls")


def test_an_export_never_replaces_a_file_and_holds_the_case_still(reviewed, tmp_path, monkeypatch):
    import os
    import sqlite3

    conn, _path = reviewed
    out = tmp_path / "taken.zip"
    out.write_bytes(b"someone else's")
    with pytest.raises(ReviewError, match="already exists"):
        export._publish(out, b"bundle")
    assert out.read_bytes() == b"someone else's"
    assert [p.name for p in tmp_path.iterdir()] == ["taken.zip"]  # no temporary file left

    def no_links(*_a: object) -> None:
        raise OSError(1, "hard links not supported")

    monkeypatch.setattr(os, "link", no_links)
    export._publish(tmp_path / "usb.zip", b"bundle")
    assert (tmp_path / "usb.zip").read_bytes() == b"bundle"
    monkeypatch.undo()

    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    seen: list[str] = []
    real = export._publish

    def during(out: Path, data: bytes) -> None:
        other = sqlite3.connect(db_path, timeout=0)
        try:
            other.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            seen.append(str(e))
        finally:
            other.close()
        real(out, data)

    monkeypatch.setattr(export, "_publish", during)
    _export(conn, tmp_path, "held.zip")
    assert seen and "locked" in seen[0]


# ---------------------------------------------------------------- Codex round 4 on #104


def _record_table(record_id: str) -> str:
    from core import pipeline
    from core.enrich.records import kind_of

    return (
        pipeline._RECORD_TABLES.get(kind_of(record_id) or "")
        or pipeline._CHECK_TABLES[record_id.split(":", 1)[0]]
    )


def test_the_thread_and_accounts_shown_beside_a_citation_are_bound(reviewed, tmp_path):
    conn, path = reviewed
    thread, sender = conn.execute(
        "SELECT m.thread_id, m.sender_account_id FROM evidence_items e"
        " JOIN messages m ON m.id = e.record_id WHERE m.sender_account_id IS NOT NULL LIMIT 1"
    ).fetchone()
    for table, rid, change in (
        ("threads", thread, lambda r: r.update(title="Another chat")),
        ("accounts", sender, lambda r: r.update(display_name="Someone else")),
    ):
        name, edit = _edit_row(table, lambda r, rid=rid: r["id"] == rid, change)
        findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
        assert FAIL in _levels(findings, "rows"), (table, _fails(findings))


def test_a_record_a_check_rests_on_is_bound(reviewed, tmp_path):
    conn, path = reviewed
    run = json.loads(zipfile.ZipFile(path).read(export.MANIFEST))["run"]
    manifest = next(
        json.loads(p)["manifest"]
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = 'pipeline.run' ORDER BY seq DESC"
        )
        if json.loads(p)["run_id"] == run["run_id"]
    )
    checks = [c for items in manifest.values() for c in items["checks"]]
    rid = next(
        r
        for c in checks
        for (ids,) in conn.execute("SELECT record_ids_json FROM check_results WHERE id = ?", (c,))
        for r in json.loads(ids)
        if not conn.execute("SELECT 1 FROM evidence_items WHERE record_id = ?", (r,)).fetchone()
    )
    name, edit = _edit_row(
        _record_table(rid), lambda r: r["id"] == rid, lambda r: r.update(locator="elsewhere")
    )
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "rows"), _fails(findings)


def test_a_logged_stipulation_cannot_be_removed_or_given_to_another_person(reviewed, tmp_path):
    conn, path = reviewed
    sid, pid = conn.execute(
        "SELECT id, person_id FROM stipulations WHERE status = 'confirmed' LIMIT 1"
    ).fetchone()
    gone = _rewrite(
        path,
        tmp_path / "b.zip",
        f"{export.TABLES}stipulations.jsonl",
        lambda t: "".join(x + "\n" for x in t.splitlines() if json.loads(x)["id"] != sid),
    )
    assert FAIL in _levels(verify_bundle(gone), "stipulations")
    name, edit = _edit_row("persons", lambda r: r["id"] == pid, lambda r: r.update(name="X Y"))
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "stipulations"), _fails(findings)


def test_malformed_rows_fail_without_a_crash(hosted, tmp_path):
    _conn, path = hosted
    name, edit = _edit_row("model_runs", lambda r: True, lambda r: r.update(params_json="{"))
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert failed(findings)


def test_a_logged_import_whose_source_is_missing_fails():
    import sqlite3

    from core.bundle import verify
    from core.db import apply_schema

    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    audit_log.append(conn, AT, EXPERT, "import", {"source_id": "src:gone", "sha256": "0" * 64})
    out = verify._Out()
    verify._inputs(conn, out, None)
    assert any(f.level == FAIL and "src:gone" in f.detail for f in out.items)


def test_the_cli_reports_an_unreadable_bundle_as_failed(tmp_path, capsys):
    from cli.main import main

    assert main(["verify-bundle", str(tmp_path / "missing.zip")]) == 1
    assert main(["verify-bundle", str(tmp_path)]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_claims_outside_the_audit_are_bound_too(tmp_path):
    from core.contracts import ClaimType
    from core.review.actions import add_claim

    conn = _build(tmp_path / "case01.db", START)
    para = conn.execute("SELECT paragraph_id FROM claims LIMIT 1").fetchone()[0]
    add_claim(conn, "C99", para, "A new claim.", ClaimType.TIMING, EXPERT, clock=lambda: AT)
    path = _export(conn, tmp_path)
    assert not failed(verify_bundle(path)), _fails(verify_bundle(path))
    name, edit = _edit_row(
        "claims", lambda r: r["id"] == "C99", lambda r: r.update(text="Something else.")
    )
    assert FAIL in _levels(verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit)), "claims")
    gone = _rewrite(
        path,
        tmp_path / "c.zip",
        f"{export.TABLES}claims.jsonl",
        lambda t: "".join(x + "\n" for x in t.splitlines() if json.loads(x)["id"] != "C99"),
    )
    assert FAIL in _levels(verify_bundle(gone), "claims")
    conn.close()


def test_an_audit_under_other_rules_is_not_exported(reviewed, tmp_path, monkeypatch):
    conn, _path = reviewed
    monkeypatch.setattr(rules, "RULE_VERSION", "9.9.9")
    with pytest.raises(ReviewError, match="Re-run the verdicts"):
        _export(conn, tmp_path, "old.zip")
    assert not (tmp_path / "old.zip").exists()


def test_a_full_audit_records_where_it_read_the_stipulations(reviewed):
    conn, _path = reviewed
    payloads = [
        json.loads(p)
        for (p,) in conn.execute("SELECT payload_json FROM audit_log WHERE action = 'pipeline.run'")
    ]
    full = [p for p in payloads if p.get("mode") != "rules_only"]
    assert full and all(isinstance(p.get("stipulations_seq"), int) for p in full)


def test_a_bundle_too_large_to_unpack_is_refused_before_reading(reviewed, monkeypatch):
    from core.bundle import verify

    _conn, path = reviewed
    monkeypatch.setattr(verify, "MAX_UNPACKED", 1000)
    findings = verify_bundle(path)
    assert _levels(findings, "files") == {FAIL}
    assert "unpack" in findings[0].detail


def test_a_bundle_file_too_large_is_refused_before_it_is_read(reviewed, monkeypatch):
    from core.bundle import verify

    _conn, path = reviewed
    monkeypatch.setattr(verify, "MAX_BUNDLE_BYTES", 1000)
    findings = verify_bundle(path)
    assert _levels(findings, "files") == {FAIL} and "bytes" in findings[0].detail


def test_a_damaged_zip_member_fails_without_a_crash(reviewed, tmp_path):
    _conn, path = reviewed
    data = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(export.REPORT)
    start = info.header_offset + 30 + len(info.filename) + len(info.extra)
    data[start + 10] ^= 0xFF  # inside the report's compressed bytes
    bad = tmp_path / "b.zip"
    bad.write_bytes(bytes(data))
    assert _levels(verify_bundle(bad), "files") == {FAIL}


def test_source_metadata_is_the_logged_imports(reviewed, tmp_path):
    conn, path = reviewed
    sid = conn.execute(
        "SELECT source_id FROM source_coverage WHERE source_id IN"
        " (SELECT json_extract(payload_json, '$.source_id') FROM audit_log WHERE action = 'import')"
        " LIMIT 1"
    ).fetchone()[0]
    for table, change in (
        ("sources", lambda r: r.update(file_name="other.xlsx")),
        (
            "source_coverage",
            lambda r: r.update(payload_json=r["payload_json"].replace("{", '{"x": 1, ', 1)),
        ),
    ):
        name, edit = _edit_row(
            table, lambda r, k=table: r[{"sources": "id"}.get(k, "source_id")] == sid, change
        )
        findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
        assert FAIL in _levels(findings, "inputs"), (table, _fails(findings))


def test_a_confirmed_links_person_keeps_the_logged_name(reviewed, tmp_path):
    conn, path = reviewed
    pid = conn.execute(
        "SELECT person_id FROM identity_links WHERE status = 'confirmed'"
    ).fetchone()[0]
    name, edit = _edit_row("persons", lambda r: r["id"] == pid, lambda r: r.update(name="Q Z"))
    findings = verify_bundle(_rewrite(path, tmp_path / "b.zip", name, edit))
    assert FAIL in _levels(findings, "identity links"), _fails(findings)


def test_the_fallback_publish_never_leaves_a_partial_file(tmp_path, monkeypatch):
    import os

    def no_links(*_a: object) -> None:
        raise OSError(1, "hard links not supported")

    def fail_replace(*_a: object) -> None:
        raise OSError(28, "disk full")

    monkeypatch.setattr(os, "link", no_links)
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        export._publish(tmp_path / "usb.zip", b"bundle")
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------- scope (Baker Product must-fix 1)


@pytest.fixture(scope="module")
def scoped(reviewed, tmp_path_factory):  # noqa: ANN001, ANN201
    """The reviewed case exported with the default scope: what the verdicts rest on."""
    conn, _full = reviewed
    return conn, _export(conn, tmp_path_factory.mktemp("bundle-scoped"), include=None)


def _member(path: Path, name: str) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        return [json.loads(x) for x in zf.read(name).decode().splitlines()]


def _rewrite_many(src: Path, dst: Path, edits: dict[str, Callable[[str], str]]) -> Path:
    """_rewrite for several files at once, rehashing each, as a careful tamperer would."""
    with zipfile.ZipFile(src) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    manifest = json.loads(files[export.MANIFEST])
    for name, edit in edits.items():
        files[name] = edit(files[name].decode("utf-8")).encode("utf-8")
        if name != export.MANIFEST:
            manifest["files"][name]["sha256"] = hashlib.sha256(files[name]).hexdigest()
    if export.MANIFEST not in edits:
        files[export.MANIFEST] = json.dumps(manifest).encode()
    with zipfile.ZipFile(dst, "w") as zf:
        for n, data in files.items():
            zf.writestr(n, data)
    return dst


def _lines(change: Callable[[list[dict]], list[dict]]) -> Callable[[str], str]:
    def edit(text: str) -> str:
        rows = change([json.loads(x) for x in text.splitlines()])
        return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)

    return edit


def test_a_bundle_by_default_holds_only_what_the_verdicts_rest_on(scoped):
    conn, path = scoped
    findings = verify_bundle(path)
    assert not failed(findings), _fails(findings)
    assert NOTE in _levels(findings, "scope") and PASS in _levels(findings, "verdicts")
    assert PASS in _levels(findings, "report") and PASS in _levels(findings, "rows")
    manifest = json.loads(zipfile.ZipFile(path).read(export.MANIFEST))
    assert manifest["scope"]["included"] == []
    dismissed = {
        eid
        for (eid,) in conn.execute(
            "SELECT evidence_id FROM evidence_reviews r WHERE seq = (SELECT MAX(seq) FROM"
            " evidence_reviews WHERE evidence_id = r.evidence_id) AND status = 'dismissed'"
        )
    }
    shipped = {r["id"] for r in _member(path, f"{export.TABLES}evidence_items.jsonl")}
    withheld = _member(path, export.WITHHELD)
    left = {w["id"] for w in withheld if w["kind"] == "evidence"}
    assert left and left <= dismissed and not left & shipped
    # every item a verdict cites ships
    cited = {
        e
        for (c,) in conn.execute("SELECT cited_json FROM verdicts")
        for e in json.loads(c).get("evidence", [])
    }
    assert cited <= shipped
    # the expert's decisions on left-out items are hashes only; the rest of the phone stays home
    stubs = [w for w in withheld if w["kind"] == "audit_log"]
    assert {w["action"] for w in stubs} == {"evidence.decide"}
    logged = _member(path, f"{export.TABLES}audit_log.jsonl")
    assert not {w["seq"] for w in stubs} & {r["seq"] for r in logged}
    # only the audit's manifests name a left-out item, by its id (which names its record)
    assert {r["action"] for r in logged for eid in left if eid in r["payload_json"]} <= {
        "pipeline.claim",
        "pipeline.run",
    }
    messages = len(_member(path, f"{export.TABLES}messages.jsonl"))
    assert 0 < messages < conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert _member(path, f"{export.TABLES}message_recipients.jsonl") == []
    report = zipfile.ZipFile(path).read(export.REPORT).decode()
    assert "Scoped reproducibility bundle" in report and "left out of this bundle" in report
    method = zipfile.ZipFile(path).read(export.METHOD).decode()
    assert "## Scope" in method and "withheld.jsonl" in method


def test_include_all_is_the_whole_case(reviewed):
    _conn, path = reviewed
    manifest = json.loads(zipfile.ZipFile(path).read(export.MANIFEST))
    assert manifest["scope"] == export.FULL and _member(path, export.WITHHELD) == []
    assert manifest["withheld"] == {"evidence": 0, "model_call": 0, "audit_log": 0}
    assert PASS in _levels(verify_bundle(path), "scope")


def test_a_scoped_hosted_case_leaves_out_the_prompts_it_does_not_rest_on(hosted, tmp_path):
    conn, _full = hosted
    path = _export(conn, tmp_path, include=None)
    findings = verify_bundle(path)
    assert not failed(findings), _fails(findings)
    logged = _member(path, f"{export.TABLES}audit_log.jsonl")
    stubs = [w for w in _member(path, export.WITHHELD) if w["kind"] == "audit_log"]
    assert not any(r["action"] == SENT_ACTION for r in logged)
    assert {w["action"] for w in stubs} >= {SENT_ACTION}
    calls = {r["id"] for r in _member(path, f"{export.TABLES}model_calls.jsonl")}
    behind = {
        cid
        for (cid,) in conn.execute(
            "SELECT mc.id FROM model_calls mc JOIN evidence_items e"
            " ON e.model_run_id = mc.model_run_id"
            " AND mc.subject_json = json_array(e.assumption_id, e.record_id)"
            " WHERE mc.outcome = 'ok' AND e.stance != 'irrelevant'"
        )
    }
    assert behind and behind <= calls
    assert calls < {r[0] for r in conn.execute("SELECT id FROM model_calls")}
    assert PASS in _levels(findings, "labels") and PASS in _levels(findings, "model calls")


@pytest.mark.parametrize(
    "tamper",
    [
        "evidence hash",  # a left-out item's hash changed: its claim's rows no longer check
        "entry hash",  # a left-out entry's hash changed: the chain breaks
        "entry dropped",  # a left-out entry no longer listed: the chain breaks
        "listed twice",  # an item both left out and shipped
        "said full",  # bundle.json calls a scoped bundle whole
        "bad line",  # a withheld line that is not one
    ],
)
def test_tampering_with_what_a_scoped_bundle_left_out_fails(scoped, tmp_path, tamper):
    _conn, path = scoped
    shipped = _member(path, f"{export.TABLES}evidence_items.jsonl")

    def change(rows: list[dict]) -> list[dict]:
        ev = next(r for r in rows if r["kind"] == "evidence")
        entry = next(r for r in rows if r["kind"] == "audit_log")
        if tamper == "evidence hash":
            ev["sha256"] = "0" * 64
        elif tamper == "entry hash":
            entry["hash"] = "0" * 64
        elif tamper == "entry dropped":
            rows.remove(entry)
        elif tamper == "listed twice":
            rows.append({"kind": "evidence", "id": shipped[0]["id"], "sha256": "1" * 64})
        elif tamper == "bad line":
            rows.append({"kind": "audit_log", "seq": "7"})
        return rows

    edits: dict[str, Callable[[str], str]] = {export.WITHHELD: _lines(change)}
    if tamper == "said full":
        edits = {
            export.MANIFEST: lambda t: json.dumps({**json.loads(t), "scope": export.FULL}),
        }
    findings = verify_bundle(_rewrite_many(path, tmp_path / "b.zip", edits))
    assert failed(findings), tamper


def test_hiding_an_item_a_verdict_rests_on_fails(scoped, tmp_path):
    """A shipped item left out and listed by its true hash still fails: the rules, re-applied
    without it, no longer give the stored verdict."""
    conn, path = scoped
    eid = next(
        e
        for (c,) in conn.execute("SELECT cited_json FROM verdicts ORDER BY id")
        for e in json.loads(c).get("evidence", [])
    )
    from core import pipeline

    sha = pipeline.evidence_sha256(conn, eid)
    logged = _member(path, f"{export.TABLES}audit_log.jsonl")
    decided = [
        r
        for r in logged
        if r["action"] == "evidence.decide" and json.loads(r["payload_json"])["evidence_id"] == eid
    ]
    stubs = [
        {"kind": "audit_log", **{k: r[k] for k in ("seq", "at_utc", "actor", "action")}}
        | {"prev_hash": r["prev_hash"], "hash": r["hash"]}
        for r in decided
    ]
    edits = {
        f"{export.TABLES}evidence_items.jsonl": _lines(
            lambda rs: [r for r in rs if r["id"] != eid]
        ),
        f"{export.TABLES}evidence_reviews.jsonl": _lines(
            lambda rs: [r for r in rs if r["evidence_id"] != eid]
        ),
        f"{export.TABLES}audit_log.jsonl": _lines(lambda rs: [r for r in rs if r not in decided]),
        export.WITHHELD: _lines(
            lambda rs: [*rs, {"kind": "evidence", "id": eid, "sha256": sha}, *stubs]
        ),
    }
    findings = verify_bundle(_rewrite_many(path, tmp_path / "b.zip", edits))
    assert FAIL in _levels(findings, "verdicts"), _fails(findings)
    assert FAIL not in _levels(findings, "rows")  # the hash alone does not give it away


def test_an_unknown_part_is_refused_and_the_preview_names_what_stays_out(reviewed, tmp_path):
    conn, _path = reviewed
    with pytest.raises(ReviewError, match="unknown bundle part"):
        export.export_bundle(
            conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=True, include="everything"
        )
    assert not (tmp_path / "x.zip").exists()
    assert export.parts("all") == export.PARTS
    assert export.parts("records, dismissed") == ("dismissed", "records")
    text = export.preview(conn, ())
    assert "Left out unless you include them" in text and "dismissed:" in text
    assert "whole case" in export.preview(conn, export.PARTS)


def test_an_export_whose_bundle_would_not_verify_writes_nothing(reviewed, tmp_path, monkeypatch):
    from core.bundle import verify

    conn, _path = reviewed
    before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    monkeypatch.setattr(
        verify, "verify_data", lambda _data: [verify.Finding(FAIL, "verdicts", "C01: differs")]
    )
    with pytest.raises(ReviewError, match="would not pass verify-bundle"):
        export.export_bundle(conn, tmp_path / "x.zip", EXPERT, counsel_confirmed=True)
    assert not (tmp_path / "x.zip").exists()
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before


def test_a_scoped_bundle_of_a_case_audited_twice_leaves_out_the_earlier_run(tmp_path):
    from core import pipeline
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl

    conn = rp.build_case("case01", tmp_path / "case01.db")
    gold = load_jsonl(rp.gold_path("case01"), GoldClaim)
    for _ in range(2):
        comps = rp.model_free_components(conn, rp.assumption_sheet("case01"), gold)
        pipeline.run_audit(conn, comps, claim_ids=[g.claim_id for g in gold][:3])
    path = _export(conn, tmp_path, include=None)
    findings = verify_bundle(path)
    assert not failed(findings), _fails(findings)
    runs = {r["pipeline_run_id"] for r in _member(path, f"{export.TABLES}verdicts.jsonl")}
    assert len(runs) == 1 < conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
    full = _export(conn, tmp_path, "full.zip", include="history")
    assert not failed(verify_bundle(full))
    assert len({r["pipeline_run_id"] for r in _member(full, f"{export.TABLES}verdicts.jsonl")}) == 2
    conn.close()
