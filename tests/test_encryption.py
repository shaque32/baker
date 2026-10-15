"""Encryption at rest: the case key, encrypted copies, the encrypted database, encrypting an
existing case, and the screen and command line around them. Synthetic data only."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import sqlite3
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import db, encryption
from core.casework import cases, protect
from core.db import CaseLocked, connect
from core.encryption import EncryptionError, WrongSecret
from core.review import audit_log
from core.review.actions import ReviewError
from eval import run_pipeline
from ui.app import App, Request

ROOT = Path(__file__).resolve().parents[1]
PASS = "correct horse battery staple"
EXPERT = "expert:Test Expert"
PORT = 8765
HOST = {"host": f"127.0.0.1:{PORT}"}
NOW = datetime(2026, 10, 13, tzinfo=UTC)


@pytest.fixture(scope="module")
def inputs(tmp_path_factory) -> dict[str, Path]:
    meta = run_pipeline.ensure_reports("case01")
    folder = tmp_path_factory.mktemp("originals")
    out = {s["source_id"]: run_pipeline.synthetic_dir("case01") / s["file"] for s in
           meta["sources"]}  # fmt: skip
    out["affidavit"] = run_pipeline.render_affidavit_pdf("case01", folder / "affidavit.pdf")
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- the case key


def test_the_real_key_derivation_is_scrypt_at_full_strength():
    kdf = encryption.Kdf()
    assert (kdf.name, kdf.n, kdf.r, kdf.p) == ("scrypt", 1 << 17, 8, 1)
    start = time.monotonic()
    key = encryption._derive(PASS, b"s" * 16, kdf)  # needs ~128 MiB; must not hit maxmem
    assert len(key) == 32 and time.monotonic() - start < 30


def test_the_key_file_opens_with_the_passphrase_or_the_recovery_key_only(tmp_path):
    kf, dek, recovery = encryption.new_key_file(PASS)
    assert encryption.open_key_file(kf, PASS) == dek
    assert encryption.open_key_file(kf, recovery) == dek
    typed = recovery.lower().replace("-", " ")  # as someone types it back off paper
    assert encryption.open_key_file(kf, typed) == dek
    last = "B" if recovery.endswith("A") else "A"  # one character off, never the real key
    for wrong in ("correct horse battery stapler", "", recovery[:-1] + last):
        with pytest.raises(WrongSecret):
            encryption.open_key_file(kf, wrong)
    text = json.dumps(kf.model_dump(mode="json"))
    assert dek.hex() not in text and PASS not in text and recovery not in text
    assert len(recovery.replace("-", "")) == 32


def test_a_tampered_key_file_opens_nothing():
    kf, _dek, _ = encryption.new_key_file(PASS)
    w = kf.wrap("passphrase")
    raw = bytearray(encryption._unb64(w.wrapped))
    raw[0] ^= 1
    bad = kf.model_copy(
        update={"wraps": [w.model_copy(update={"wrapped": encryption._b64(bytes(raw))})]}
    )
    with pytest.raises(WrongSecret):
        encryption.open_key_file(bad, PASS)
    moved = kf.model_copy(update={"key_id": "0" * 32})  # a wrap is bound to its key id
    with pytest.raises(WrongSecret):
        encryption.open_key_file(moved, PASS)


def test_passphrase_rules():
    with pytest.raises(ValueError, match="at least 12"):
        encryption.check_new_passphrase("short")
    with pytest.raises(ValueError, match="do not match"):
        encryption.check_new_passphrase(PASS, PASS + "x")
    assert encryption.check_new_passphrase("ｆｕｌｌ width pass") == "full width pass"


def test_changing_the_passphrase_rewraps_the_same_key(tmp_path):
    dbp = tmp_path / "case.db"
    recovery = encryption.create_key(dbp, PASS)
    _, dek = encryption.case_key(dbp)
    encryption.change_passphrase(dbp, PASS, "a different long passphrase")
    kf = encryption.read_key_file(encryption.key_path(dbp))
    assert encryption.open_key_file(kf, "a different long passphrase") == dek
    assert encryption.open_key_file(kf, recovery) == dek
    with pytest.raises(WrongSecret):
        encryption.open_key_file(kf, PASS)


# ---------------------------------------------------------------- encrypted files


def _keyed() -> tuple[str, bytes]:
    key_id, dek = os.urandom(16).hex(), os.urandom(32)
    encryption.remember(key_id, dek)
    return key_id, dek


@pytest.mark.parametrize("size", [0, 1, 63, 64, 65, 64 * 3, 64 * 3 + 5, 1000])
def test_files_round_trip_with_random_access(tmp_path, size):
    key_id, dek = _keyed()
    data = os.urandom(size)
    src, dst = tmp_path / "plain.bin", tmp_path / "enc.bin"
    src.write_bytes(data)
    sha = encryption.encrypt_file(src, dst, key_id, dek, chunk=64)
    assert sha == hashlib.sha256(data).hexdigest() == encryption.plain_sha256(dst)
    assert encryption.input_size(dst) == size and encryption.is_encrypted_file(dst)
    with encryption.open_input(dst) as f:
        assert f.read() == data
        for pos, n in [(0, 10), (size // 2, 70), (max(size - 3, 0), 10), (size + 5, 4)]:
            f.seek(pos)
            assert f.read(n) == data[pos : pos + n]
        f.seek(-min(size, 7), io.SEEK_END)
        assert f.read() == data[size - min(size, 7) :]


def test_a_zip_reads_through_decryption(tmp_path):
    key_id, dek = _keyed()
    src = tmp_path / "pkg.zip"
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.xml", "<synthetic>" + "x" * 50_000 + "</synthetic>")
        z.writestr("files/img.bin", os.urandom(200_000))
    dst = tmp_path / "pkg.enc"
    encryption.encrypt_file(src, dst, key_id, dek, chunk=4096)
    with encryption.open_input(dst) as f, zipfile.ZipFile(f) as z:
        assert z.read("report.xml").startswith(b"<synthetic>")
        assert len(z.read("files/img.bin")) == 200_000
    assert b"PK\x03\x04" not in dst.read_bytes()


def _encrypted(tmp_path: Path, data: bytes, name: str = "enc.bin") -> tuple[Path, str, bytes]:
    key_id, dek = _keyed()
    src = tmp_path / f"{name}.plain"
    src.write_bytes(data)
    dst = tmp_path / name
    encryption.encrypt_file(src, dst, key_id, dek, chunk=64)
    return dst, key_id, dek


def _read_all(path: Path) -> bytes:
    with encryption.open_input(path) as f:
        return f.read()


def test_damaged_cut_or_reordered_files_fail_to_read(tmp_path):
    data = os.urandom(64 * 4 + 10)
    enc, key_id, dek = _encrypted(tmp_path, data)
    good = enc.read_bytes()
    h, stored = encryption.HEADER_SIZE, 64 + encryption.NONCE + encryption.TAG

    def bad(raw: bytes) -> None:
        enc.write_bytes(raw)
        with pytest.raises(EncryptionError):
            _read_all(enc)

    flipped = bytearray(good)
    flipped[h + 20] ^= 1
    bad(bytes(flipped))
    bad(good[: h + 4 * stored])  # the last (short) chunk dropped
    bad(good[: h + 3 * stored])  # cut at a chunk boundary
    bad(good[:-1])
    chunks = [good[h + i * stored : h + (i + 1) * stored] for i in range(4)]
    bad(good[:h] + chunks[1] + chunks[0] + good[h + 2 * stored :])
    other, _, _ = _encrypted(tmp_path, data, "other.bin")  # same key, another file
    bad(good[:h] + other.read_bytes()[h : h + stored] + good[h + stored :])
    enc.write_bytes(good)
    assert _read_all(enc) == data


def test_a_locked_case_key_reads_no_file(tmp_path):
    enc, key_id, _ = _encrypted(tmp_path, b"synthetic bytes" * 10)
    encryption.forget(key_id)
    with pytest.raises(CaseLocked):
        _read_all(enc)


def test_a_plain_file_opens_as_itself(tmp_path):
    p = tmp_path / "plain.xlsx"
    p.write_bytes(b"PK\x03\x04 synthetic")
    with encryption.open_input(p) as f:
        assert f.read() == p.read_bytes()
    assert encryption.input_size(p) == p.stat().st_size and not encryption.is_encrypted_file(p)


# ---------------------------------------------------------------- the database


def test_a_new_database_beside_a_key_file_is_encrypted(tmp_path):
    dbp = tmp_path / "case.db"
    recovery = encryption.create_key(dbp, PASS)
    conn = connect(dbp)
    assert db.is_encrypted(conn)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES ('SYNTHETIC-MARKER-7731')")
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE t SET x = 'SYNTHETIC-MARKER-7731 again'")
    for f in tmp_path.iterdir():  # the database and its rollback journal, mid-transaction
        assert b"SYNTHETIC-MARKER-7731" not in f.read_bytes(), f.name
    conn.rollback()
    conn.close()
    assert not dbp.read_bytes().startswith(encryption.SQLITE_HEADER)
    encryption.forget_all()
    with pytest.raises(CaseLocked, match="locked"):
        connect(dbp)
    encryption.unlock(dbp, recovery)
    assert connect(dbp).execute("SELECT x FROM t").fetchone() == ("SYNTHETIC-MARKER-7731",)


def test_a_key_file_from_another_case_does_not_open_the_database(tmp_path):
    a, b = tmp_path / "a" / "case.db", tmp_path / "b" / "case.db"
    a.parent.mkdir()
    b.parent.mkdir()
    for p in (a, b):
        encryption.create_key(p, PASS)
        conn = connect(p)
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        conn.close()
    encryption.key_path(b).replace(encryption.key_path(a))
    with pytest.raises(CaseLocked, match="does not open with this case's key"):
        connect(a)
    encryption.key_path(a).unlink()
    with pytest.raises(CaseLocked, match="key file case.key is missing"):
        connect(a)


def test_a_plain_case_database_opens_exactly_as_before(tmp_path):
    dbp = tmp_path / "case.db"
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES ('synthetic')")
    conn.commit()
    conn.close()
    before = (_sha(dbp), dbp.stat().st_mtime_ns)
    conn = connect(dbp)
    assert type(conn) is sqlite3.Connection and not db.is_encrypted(conn)
    assert conn.execute("SELECT x FROM t").fetchall() == [("synthetic",)]
    conn.close()
    assert (_sha(dbp), dbp.stat().st_mtime_ns) == before
    assert not encryption.key_path(dbp).exists()


def test_both_database_modules_errors_are_caught():
    import sqlcipher3.dbapi2 as cipher

    for name in ("Error", "OperationalError", "IntegrityError"):
        assert getattr(sqlite3, name) in getattr(db, name)
        assert getattr(cipher, name) in getattr(db, name)


def test_no_code_catches_only_the_standard_modules_database_errors():
    """SQLCipher raises its own classes, so `except sqlite3.OperationalError` would miss an
    encrypted case's errors. Catch core.db.Error / OperationalError / IntegrityError."""
    found = []
    for folder in ("core", "ui", "cli"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.type is not None:
                    for sub in ast.walk(node.type):
                        if (
                            isinstance(sub, ast.Attribute)
                            and isinstance(sub.value, ast.Name)
                            and sub.value.id == "sqlite3"
                        ):
                            found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not found, found


# ---------------------------------------------------------------- cases


def _upload(case: cases.Case, src: Path) -> Path:
    """What the screen does with an upload: written (encrypted for an encrypted case) into
    inputs/ and hashed as it goes."""
    up = cases.upload_path(case)
    wrap = cases.input_writer(case)
    sha = hashlib.sha256()
    with up.open("xb") as f:
        w = wrap(f) if wrap else f
        data = src.read_bytes()
        sha.update(data)
        w.write(data)
        if w is not f:
            w.close()
    return up


def _import(case: cases.Case, src: Path, kind: str) -> cases.Imported:
    conn = connect(case.db)
    try:
        return cases.import_upload(
            case, conn, _upload(case, src), _sha(src), src.name, kind, EXPERT, clock=lambda: NOW
        )
    finally:
        conn.close()


def _plain_case(home: Path, inputs: dict[str, Path], name: str = "Synthetic plain") -> cases.Case:
    case = cases.create_case(home, name, EXPERT, clock=lambda: NOW)
    _import(case, inputs["affidavit"], "govdoc")
    for sid in ("item1", "item2"):
        _import(case, inputs[sid], "report")
    return case


def _dump(conn: sqlite3.Connection) -> dict[str, list]:
    out = {}
    for t in protect._tables(conn):
        rows = conn.execute(f'SELECT * FROM "{t}"').fetchall()  # noqa: S608
        out[t] = sorted(rows, key=repr)
    return out


def _marker(conn: sqlite3.Connection) -> bytes:
    body = conn.execute(
        "SELECT body FROM messages WHERE length(body) >= 16 ORDER BY id LIMIT 1"
    ).fetchone()[0]
    return body.encode("utf-8")


def _no_plain_case_data(case: cases.Case, marker: bytes, inputs: dict[str, Path]) -> None:
    for f in case.folder.rglob("*"):
        if not f.is_file() or f.name == "case.json":
            continue
        raw = f.read_bytes()
        assert marker not in raw, f"{f.name} holds plain case data"
        assert not raw.startswith((b"PK\x03\x04", b"%PDF", encryption.SQLITE_HEADER)), f.name
    for src in inputs.values():
        chunk = src.read_bytes()[1000:1100]
        for f in case.inputs.iterdir():
            assert chunk not in f.read_bytes()


def test_an_encrypted_case_imports_and_keeps_only_encrypted_copies(tmp_path, inputs):
    case = cases.create_case(tmp_path, "Synthetic encrypted", EXPERT, passphrase=PASS)
    recovery = cases.recovery_key_for(case)
    assert recovery is not None and cases.recovery_key_for(case) is None  # shown once
    got = _import(case, inputs["item1"], "report")
    assert got.sha256 == _sha(inputs["item1"])
    _import(case, inputs["affidavit"], "govdoc")
    conn = connect(case.db)
    marker = _marker(conn)
    rows = dict(conn.execute("SELECT id, sha256 FROM sources").fetchall())
    log = [json.loads(p) for (p,) in conn.execute("SELECT payload_json FROM audit_log")]
    conn.close()
    assert rows["item1"] == _sha(inputs["item1"])
    assert log[0] == {"name": "Synthetic encrypted", "encrypted": True}
    assert protect.state(case) == "encrypted"
    _no_plain_case_data(case, marker, {k: inputs[k] for k in ("item1", "affidavit")})
    with pytest.raises(ReviewError, match="already in the case"):
        _import(case, inputs["item1"], "report")
    assert sorted(p.name for p in case.inputs.iterdir()) == ["affidavit.pdf", "item1.xlsx"]


def test_encrypting_an_existing_case_keeps_every_row_and_file(tmp_path, inputs):
    case = _plain_case(tmp_path, inputs)
    conn = connect(case.db)
    before, marker = _dump(conn), _marker(conn)
    conn.close()
    shas = {p.name: _sha(p) for p in case.inputs.iterdir()}

    done = protect.encrypt_case(case, PASS, EXPERT, again=PASS, clock=lambda: NOW)
    assert (done.files, done.database, done.resumed) == (3, True, False)
    assert protect.state(case) == "encrypted"
    _no_plain_case_data(case, marker, inputs)
    assert {p.name: encryption.plain_sha256(p) for p in case.inputs.iterdir()} == shas
    assert not list(case.folder.glob(".*encrypting"))
    assert not list(case.inputs.glob(".*"))

    conn = connect(case.db)
    after = _dump(conn)
    last = conn.execute("SELECT actor, action, payload_json FROM audit_log ORDER BY seq DESC")
    actor, action, payload = last.fetchone()
    assert audit_log.verify_chain(conn)
    conn.close()
    assert (actor, action) == (EXPERT, "case.encrypt")
    assert json.loads(payload)["inputs_encrypted"] == 3
    before["audit_log"] = sorted([*before["audit_log"]], key=repr)
    assert {t: r for t, r in after.items() if t != "audit_log"} == {
        t: r for t, r in before.items() if t != "audit_log"
    }
    assert set(before["audit_log"]) < set(after["audit_log"])

    encryption.forget_all()
    with pytest.raises(CaseLocked):
        connect(case.db)
    encryption.unlock(case.db, done.recovery_key)
    connect(case.db).close()
    with pytest.raises(ReviewError, match="already encrypted"):
        protect.encrypt_case(case, PASS, EXPERT)


def test_encryption_refuses_a_weak_passphrase_or_a_running_audit(tmp_path, inputs):
    case = cases.create_case(tmp_path, "Synthetic busy", EXPERT)
    with pytest.raises(ReviewError, match="do not match"):
        protect.encrypt_case(case, PASS, EXPERT, again=PASS + "!")
    with pytest.raises(ReviewError, match="at least 12"):
        protect.encrypt_case(case, "short", EXPERT, again="short")
    conn = connect(case.db)
    conn.execute(
        "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version,"
        " contracts_version, rule_version, config_json)"
        " VALUES ('run:1', '2026-10-13T00:00:00Z', 'running', '0', '0', '0', '{}')"
    )
    conn.commit()
    conn.close()
    with pytest.raises(ReviewError, match="audit is recorded as running"):
        protect.encrypt_case(case, PASS, EXPERT, again=PASS)
    assert protect.state(case) == "plain" and not encryption.key_path(case.db).exists()


def test_an_interrupted_encryption_still_opens_and_finishes(tmp_path, inputs, monkeypatch):
    case = _plain_case(tmp_path, inputs)
    conn = connect(case.db)
    before = _dump(conn)
    conn.close()
    real = protect._replace

    def fail_on_database(src: Path, dst: Path) -> None:
        if dst == case.db:
            raise OSError("synthetic crash before the database is swapped")
        real(src, dst)

    monkeypatch.setattr(protect, "_replace", fail_on_database)
    with pytest.raises(OSError, match="synthetic crash"):
        protect.encrypt_case(case, PASS, EXPERT, again=PASS)
    assert protect.state(case) == "partial"
    assert all(encryption.is_encrypted_file(p) for p in case.inputs.iterdir())
    assert encryption.database_is_plain(case.db) and not list(case.folder.glob(".*encrypting"))
    conn = connect(case.db)  # still the plain database, unchanged
    assert _dump(conn) == before
    conn.close()

    monkeypatch.setattr(protect, "_replace", real)
    encryption.forget_all()
    with pytest.raises(ReviewError, match="did not finish"):
        protect.encrypt_case(case, "a passphrase never chosen", EXPERT)
    done = protect.encrypt_case(case, PASS, EXPERT)
    assert done.resumed and done.database and done.files == 0
    assert protect.state(case) == "encrypted"
    encryption.forget_all()
    encryption.unlock(case.db, done.recovery_key)  # the new recovery key opens it
    conn = connect(case.db)
    assert {t: r for t, r in _dump(conn).items() if t != "audit_log"} == {
        t: r for t, r in before.items() if t != "audit_log"
    }
    conn.close()


def test_the_audit_runs_the_same_on_an_encrypted_case(tmp_path):
    spec = run_pipeline.assumption_sheet("case01")
    plain_out, enc_out = tmp_path / "plain", tmp_path / "enc"
    plain = run_pipeline.run_once("case01", "model-free", "none", plain_out, spec, "simulated")
    enc_out.mkdir()
    encryption.create_key(enc_out / "case01.db", PASS)
    encrypted = run_pipeline.run_once("case01", "model-free", "none", enc_out, spec, "simulated")
    conn = connect(enc_out / "case01.db")
    assert db.is_encrypted(conn)
    conn.close()
    assert [p.model_dump() for p in encrypted] == [p.model_dump() for p in plain]


# ---------------------------------------------------------------- the screen


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def send_file(app: App, path: Path, kind: str):  # noqa: ANN201
    b = "baker-test-boundary-enc"
    body = b"".join(
        [
            *(
                f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
                for k, v in {"token": app.token, "kind": kind}.items()
            ),
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode()
            + path.read_bytes()
            + b"\r\n",
            f"--{b}--\r\n".encode(),
        ]
    )
    req = Request(
        "POST", "/case/import", {}, {**HOST, "content-type": f"multipart/form-data; boundary={b}"}
    )
    return app.handle_upload(req, io.BytesIO(body), len(body))


@pytest.fixture
def app(tmp_path) -> App:
    a = App(home=tmp_path / "cases", port=PORT, model_check=None)
    post(a, "/expert", name="Test Expert")
    return a


def test_screen_makes_an_encrypted_case_shows_its_recovery_key_once_and_locks(app, inputs):
    r = post(app, "/case/new", name="Synthetic screen", encrypt="1", passphrase=PASS,
             passphrase2=PASS)  # fmt: skip
    assert r.header("Location") == "/setup#recovery"
    case = app.case
    assert case is not None and protect.state(case) == "encrypted"
    page = get(app, "/setup").text
    key = app.recovery[1]  # type: ignore[index]
    assert key in page and "Write down this case" in page and "Lock this case now" in page
    post(app, "/case/recovery/done", next="/setup")
    assert key not in get(app, "/setup").text

    assert send_file(app, inputs["item1"], "report").status == 303
    assert "Imported item1.xlsx" in get(app, "/setup").text
    assert encryption.is_encrypted_file(case.inputs / "item1.xlsx")

    assert post(app, "/case/lock").header("Location") == "/cases"
    assert app.case is None and protect.is_locked(case)
    listing = get(app, "/cases").text
    assert "Encrypted, locked" in listing and "Passphrase or recovery key" in listing
    post(app, "/case/open", case=case.folder.name, passphrase="not the passphrase at all")
    assert app.case is None
    assert "does not open this case" in get(app, "/cases").text
    post(app, "/case/open", case=case.folder.name, passphrase=key)
    assert app.case == case and "Unlocked and opened" in get(app, "/setup").text


def test_screen_encrypts_an_existing_case_on_request_only(app, inputs, tmp_path):
    post(app, "/case/new", name="Synthetic old case")  # unchecked box: a plain case
    case = app.case
    assert case is not None and protect.state(case) == "plain"
    assert send_file(app, inputs["item2"], "report").status == 303
    assert not encryption.is_encrypted_file(case.inputs / "item2.xlsx")
    page = get(app, "/setup").text
    assert "not encrypted" in page and "Encrypt this case" in page
    assert "Not encrypted" in get(app, "/cases").text

    post(app, "/case/encrypt", passphrase=PASS, passphrase2="something else entirely")
    assert protect.state(case) == "plain"
    r = post(app, "/case/encrypt", passphrase=PASS, passphrase2=PASS)
    assert r.header("Location") == "/setup#recovery"
    assert protect.state(case) == "encrypted"
    page = get(app, "/setup").text
    assert app.recovery is not None and app.recovery[1] in page
    assert "Encrypted" in get(app, "/cases").text

    post(app, "/case/passphrase", current=PASS, new="a brand new passphrase",
         new2="a brand new passphrase")  # fmt: skip
    assert "Passphrase changed" in get(app, "/setup").text
    post(app, "/case/lock")
    post(app, "/case/open", case=case.folder.name, passphrase="a brand new passphrase")
    assert app.case == case


def test_screen_on_one_encrypted_database_asks_for_its_passphrase(tmp_path):
    case = cases.create_case(tmp_path, "Synthetic single", EXPERT, passphrase=PASS)
    encryption.forget_all()
    a = App(db_path=case.db, port=PORT, model_check=None)
    assert a.case is None
    assert get(a, "/").header("Location") == "/cases"
    assert "encrypted and locked" in get(a, "/cases").text
    post(a, "/case/open", passphrase=PASS)
    assert a.case == case and get(a, "/").status == 200


def test_a_plain_case_opens_on_the_screen_with_no_key_file(app, inputs):
    post(app, "/case/new", name="Synthetic plain screen")
    case = app.case
    assert case is not None
    send_file(app, inputs["affidavit"], "govdoc")
    post(app, "/case/open", case=case.folder.name)
    assert get(app, "/").status == 200
    assert not encryption.key_path(case.db).exists()
    assert encryption.database_is_plain(case.db)


# ---------------------------------------------------------------- the command line


def test_command_line_encrypts_and_asks_for_the_passphrase(tmp_path, inputs, monkeypatch, capsys):
    from cli import main as cli

    case = _plain_case(tmp_path, inputs, "Synthetic cli")
    typed = iter([PASS, PASS])
    monkeypatch.setattr(cli, "_ask", lambda prompt: next(typed))
    assert cli.main(["encrypt", "--db", str(case.db), "--by", EXPERT]) == 0
    out = capsys.readouterr().out
    assert "Recovery key:" in out and protect.state(case) == "encrypted"
    encryption.forget_all()

    typed = iter(["wrong passphrase here", PASS])
    monkeypatch.setattr(cli, "_ask", lambda prompt: next(typed))
    assert cli.main(["verify-log", "--db", str(case.db)]) == 0
    assert "does not open this case" in capsys.readouterr().err

    typed = iter([PASS, "another long passphrase", "another long passphrase"])
    monkeypatch.setattr(cli, "_ask", lambda prompt: next(typed))
    assert cli.main(["passphrase", "--db", str(case.db), "--by", EXPERT]) == 0
    encryption.forget_all()
    assert encryption.unlock(case.db, "another long passphrase")
