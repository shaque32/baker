"""The per-PR changelog entries in docs/changelog/ and the tool that reads them as one log."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("changelog", ROOT / "tools" / "changelog.py")
changelog = importlib.util.module_from_spec(_spec)
sys.modules["changelog"] = changelog
_spec.loader.exec_module(changelog)

GOOD = """## {date}: {title} (#90)
- Changed: something, and why it
  needed changing.
- Where: PR #90
- Verified: tests
- Open: nothing known
- Affects: none
- Status doc: {status}
"""


def _write(d: Path, name: str, date: str, title: str = "A change", status: str = "no change"):
    (d / name).write_text(GOOD.format(date=date, title=title, status=status), encoding="utf-8")


def test_repo_entries_are_well_formed():
    entries, errors = changelog.load()
    assert errors == []
    assert entries, "docs/changelog/ has at least one entry"


def test_newest_first_by_date_then_name(tmp_path):
    _write(tmp_path, "2026-10-14-old.md", "2026-10-14")
    _write(tmp_path, "2026-10-16-b.md", "2026-10-16")
    _write(tmp_path, "2026-10-16-a.md", "2026-10-16")
    (tmp_path / "README.md").write_text("not an entry", encoding="utf-8")
    entries, errors = changelog.load(tmp_path)
    assert errors == []
    assert [e.path.name for e in entries] == [
        "2026-10-16-b.md",
        "2026-10-16-a.md",
        "2026-10-14-old.md",
    ]


@pytest.mark.parametrize(
    ("name", "text", "needle"),
    [
        ("Bad_Name.md", "", "name must be"),
        ("2026-10-16-x.md", GOOD.format(date="2026-10-15", title="t", status="no change"), "first"),
        (
            "2026-10-16-x.md",
            GOOD.format(date="2026-10-16", title="t", status="no change").replace(
                "- Open: nothing known\n", ""
            ),
            "'- Open:'",
        ),
        ("2026-10-16-x.md", GOOD.format(date="2026-10-16", title="t", status="maybe"), "Status"),
        (
            "2026-10-16-x.md",
            GOOD.format(date="2026-10-16", title="t", status="no change") * 2,
            "one entry per file",
        ),
    ],
)
def test_malformed_entries_are_reported(tmp_path, name, text, needle):
    (tmp_path / name).write_text(text, encoding="utf-8")
    entries, errors = changelog.load(tmp_path)
    assert entries == []
    assert any(needle in e for e in errors), errors


def test_build_puts_entries_between_preface_and_archive(tmp_path):
    archive = tmp_path / "CHANGELOG_AI.md"
    archive.write_text("# Log\n\nPreface.\n\n---\n\n## 2026-10-01: Old entry\n- x\n")
    entries = tmp_path / "entries"
    entries.mkdir()
    _write(entries, "2026-10-16-new.md", "2026-10-16", title="New entry")
    out = changelog.build(entries, archive)
    assert out.index("Preface.") < out.index("New entry") < out.index("Old entry")


def test_build_of_the_repo_keeps_every_archive_entry():
    out = changelog.build()
    archive = (ROOT / "docs" / "CHANGELOG_AI.md").read_text(encoding="utf-8")
    for line in archive.splitlines():
        if line.startswith("## 20"):
            assert line in out


def test_pending_lists_only_pending(tmp_path, capsys):
    _write(tmp_path, "2026-10-16-a.md", "2026-10-16", status="pending: §8 add a row")
    _write(tmp_path, "2026-10-16-b.md", "2026-10-16", status="applied 2026-10-17")
    _write(tmp_path, "2026-10-16-c.md", "2026-10-16", status="no change")
    assert changelog.main(["pending", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "2026-10-16-a.md" in out
    assert "-b.md" not in out and "-c.md" not in out


def test_check_fails_on_a_bad_entry(tmp_path):
    (tmp_path / "2026-10-16-x.md").write_text("## 2026-10-16: no fields\n", encoding="utf-8")
    assert changelog.main(["check", "--dir", str(tmp_path)]) == 1
