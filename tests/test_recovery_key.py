"""A case never loses its only recovery key without saying so (2026-11-04 walkthrough): Lock
waits until the key is written down, a key never confirmed is flagged after a restart, a new key
can be made with the passphrase, and an unfinished encryption is named in the case list."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import encryption
from core.casework import protect
from tests.test_encryption import PASS, get, post


@pytest.fixture
def make_app(tmp_path: Path):  # noqa: ANN201
    from ui.app import App

    def make() -> App:
        a = App(home=tmp_path / "cases", port=8765, model_check=None)
        post(a, "/expert", name="Test Expert")
        return a

    return make


def _new_encrypted(app):  # noqa: ANN001, ANN202
    post(app, "/case/new", name="Key case", encrypt="1", passphrase=PASS, passphrase2=PASS)
    return app.case, app.recovery[1]


def test_lock_waits_until_the_recovery_key_is_written_down(make_app):
    app = make_app()
    case, key = _new_encrypted(app)
    post(app, "/case/lock")
    assert app.case == case and not protect.is_locked(case)  # refused, nothing lost
    assert "written it down" in (app.flash[0] if app.flash else get(app, "/setup").text)
    assert key in get(app, "/setup").text
    post(app, "/case/recovery/done", next="/setup")
    assert not protect.recovery_unconfirmed(case)
    post(app, "/case/lock")
    assert app.case is None and protect.is_locked(case)


def test_a_key_never_written_down_is_flagged_after_a_restart_and_a_new_one_works(make_app):
    app = make_app()
    case, old_key = _new_encrypted(app)
    assert protect.recovery_unconfirmed(case)
    protect.lock(case)  # the screen stops before "I have written it down"
    app = make_app()  # a restart: the key is gone from memory
    post(app, "/case/open", case=case.folder.name, passphrase=PASS)
    page = get(app, "/setup").text
    assert "may have no usable recovery key" in page and "Make a new recovery key" in page
    post(app, "/case/recovery/new", passphrase="not the passphrase at all")
    assert app.recovery is None
    post(app, "/case/recovery/new", passphrase=PASS)
    new_key = app.recovery[1]
    assert new_key != old_key and new_key in get(app, "/setup").text
    post(app, "/case/recovery/done", next="/setup")
    assert "may have no usable recovery key" not in get(app, "/setup").text
    protect.lock(case)
    with pytest.raises(encryption.WrongSecret):
        encryption.unlock(case.db, old_key)
    encryption.unlock(case.db, new_key)


def test_an_unfinished_encryption_is_named_in_the_case_list(make_app):
    app = make_app()
    post(app, "/case/new", name="Half case")
    case = app.case
    encryption.create_key(case.db, PASS)  # a key file, but the database is still plain
    assert protect.state(case) == "partial"
    listing = get(app, "/cases").text
    assert "Encryption not finished" in listing and "still readable on disk" in listing


def test_the_cloud_key_line_names_where_the_key_is_and_it_can_be_removed(tmp_path, monkeypatch):
    from core.llm import cloud
    from ui.app import App

    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    monkeypatch.delenv("BAKER_ANTHROPIC_API_KEY", raising=False)
    config = tmp_path / "cloud.json"
    app = App(home=tmp_path / "cases", port=8765, model_check=None, cloud_config=config)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Plain case")
    post(app, "/cloud/key", api_key="sk-ant-FAKE-test-000000000000")
    assert "saved on this computer, not encrypted" in get(app, "/setup").text
    post(app, "/case/new", name="Sealed case", encrypt="1", passphrase=PASS, passphrase2=PASS)
    post(app, "/case/recovery/done", next="/setup")
    page = get(app, "/setup").text
    assert "not encrypted" in page and "seal one in this case instead" in page
    post(app, "/cloud/key", api_key="sk-ant-FAKE-sealed-00000000000")
    assert "saved in this case, encrypted" in get(app, "/setup").text
    post(app, "/cloud/key/remove")
    assert "saved on this computer, not encrypted" in get(app, "/setup").text  # the file's
    post(app, "/cloud/key/remove")
    assert (
        "No cloud key yet" in get(app, "/setup").text
        and "Paste your firm" in get(app, "/setup").text
    )
