"""tools/pilot_link.py: presigned R2 download links (signing is local, no network)."""

from __future__ import annotations

import datetime
import importlib.util
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pilot_link", ROOT / "tools" / "pilot_link.py")
pilot_link = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot_link)

NOW = datetime.datetime(2013, 5, 24, tzinfo=datetime.UTC)
ENV = {
    "R2_ACCOUNT_ID": "acct123",
    "R2_ACCESS_KEY_ID": "AKID",
    "R2_SECRET_ACCESS_KEY": "secret",
    "R2_BUCKET": "pilot-installers",
}


def test_matches_the_aws_sigv4_presigned_url_example():
    # The worked example in AWS's "Authenticating Requests: Using Query Parameters" docs.
    url = pilot_link.presign(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        path="/test.txt",
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        expires=86400,
        now=NOW,
    )
    assert url.endswith(
        "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
    )


def test_r2_link_is_path_style_with_region_auto():
    url = pilot_link.r2_link(ENV, "Mabillon Setup 0.1.0.exe", 3 * 86400, NOW)
    parts = urllib.parse.urlsplit(url)
    assert parts.netloc == "acct123.r2.cloudflarestorage.com"
    assert parts.path == "/pilot-installers/Mabillon%20Setup%200.1.0.exe"
    q = urllib.parse.parse_qs(parts.query)
    assert q["X-Amz-Credential"] == ["AKID/20130524/auto/s3/aws4_request"]
    assert q["X-Amz-Expires"] == ["259200"]
    assert "secret" not in url


def test_longer_than_seven_days_is_refused():
    with pytest.raises(ValueError):
        pilot_link.r2_link(ENV, "a.exe", 7 * 86400 + 1, NOW)
    with pytest.raises(SystemExit):
        pilot_link.main(["a.exe", "--days", "8"])


def test_missing_settings_are_named(monkeypatch):
    for name in pilot_link.ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="R2_ACCOUNT_ID, R2_ACCESS_KEY_ID"):
        pilot_link.main(["a.exe"])


def test_prints_one_link(monkeypatch, capsys):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert pilot_link.main(["a.exe", "--hours", "12"]) == 0
    out = capsys.readouterr()
    assert out.out.count("https://") == 1
    assert "X-Amz-Expires=43200" in out.out
    assert "Works until" in out.err
