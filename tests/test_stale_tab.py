"""A page left open in another tab acts only on the case it was drawn for, and a page from
before a restart says so instead of a bare refusal (the 2026-11-04 real-app walkthrough)."""

from __future__ import annotations

import io
import re
from pathlib import Path

from core.casework import cloud as cloud_policy
from core.db import connect
from ui.app import App, Request

HOST = {"host": "127.0.0.1:8765"}


def _app(tmp_path: Path) -> App:
    return App(home=tmp_path / "cases", port=8765, model_check=None,
               cloud_config=tmp_path / "cloud.json")  # fmt: skip


def get(app: App, path: str, **query: str):  # noqa: ANN201
    return app.handle(Request("GET", path, dict(query), dict(HOST)))


def post(app: App, path: str, **form: str):  # noqa: ANN201
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def _for_case(page: str) -> str:
    found = set(re.findall(r'name="for_case" value="([^"]+)"', page))
    found |= set(re.findall(r"name='for_case' value='([^']+)'", page))
    assert len(found) == 1, found
    return found.pop()


def _two_cases(app: App) -> tuple[str, str]:
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Case one")
    one = _for_case(get(app, "/setup").text)
    post(app, "/case/new", name="Case two")
    two = _for_case(get(app, "/setup").text)
    assert one != two
    return one, two


def test_a_form_from_another_cases_page_is_refused_and_saves_nothing(tmp_path):
    app = _app(tmp_path)
    one, _ = _two_cases(app)  # case two is open now, as if a second tab opened it
    assert app.case is not None and app.case.name == "Case two"
    r = post(app, "/cloud/case", allowed="1", for_case=one)
    assert r.status == 303
    msg = app.flash[0] if app.flash else ""
    assert "Nothing was saved" in msg and "Case one" in msg and "Case two" in msg
    conn = connect(app.case.db)
    try:
        assert not cloud_policy.case_cloud(conn).get("allowed")
    finally:
        conn.close()


def test_a_form_for_the_open_case_still_works(tmp_path):
    app = _app(tmp_path)
    _, two = _two_cases(app)
    post(app, "/cloud/case", allowed="1", for_case=two)
    conn = connect(app.case.db)
    try:
        assert cloud_policy.case_cloud(conn).get("allowed")
    finally:
        conn.close()


def test_an_upload_from_another_cases_page_is_refused(tmp_path):
    app = _app(tmp_path)
    one, _ = _two_cases(app)
    b = "stale-tab-boundary"
    body = (
        f'--{b}\r\nContent-Disposition: form-data; name="token"\r\n\r\n{app.token}\r\n'
        f'--{b}\r\nContent-Disposition: form-data; name="for_case"\r\n\r\n{one}\r\n'
        f'--{b}\r\nContent-Disposition: form-data; name="kind"\r\n\r\nreport\r\n'
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="x.xlsx"\r\n'
        "Content-Type: application/octet-stream\r\n\r\nnot a workbook\r\n"
        f"--{b}--\r\n"
    ).encode()
    req = Request("POST", "/case/import", {}, {**HOST, "content-type":
                  f"multipart/form-data; boundary={b}"})  # fmt: skip
    r = app.handle_upload(req, io.BytesIO(body), len(body))
    assert r.status == 303
    assert app.flash and "Case one" in app.flash[0]
    assert not list(app.case.inputs.glob("*")) if app.case.inputs.exists() else True


def test_a_page_from_before_a_restart_explains_itself_with_a_way_back(tmp_path):
    app = _app(tmp_path)
    post(app, "/expert", name="Test Expert")
    post(app, "/case/new", name="Case one")
    r = post(app, "/case/lock", token="token-from-an-earlier-start")
    assert r.status == 403
    assert "Mabillon was restarted" in r.text and "nothing was saved" in r.text
    assert "href='/'" in r.text or "href='/cases'" in r.text
