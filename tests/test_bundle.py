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
    return export.export_bundle(
        conn, tmp_path / name, EXPERT, counsel_confirmed=True, clock=lambda: AT
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
