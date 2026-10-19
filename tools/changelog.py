"""The AI changelog: one entry file per PR in docs/changelog/, read as one log.

Each PR adds its own file instead of editing a shared one, so open PRs stop conflicting with
each other after every merge. docs/changelog/README.md gives the format.

    python tools/changelog.py check      # every entry file is well formed (run by the tests)
    python tools/changelog.py build      # the whole log, newest first, entry files then archive
    python tools/changelog.py pending    # entries the status refresh still has to apply
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY_DIR = ROOT / "docs" / "changelog"
ARCHIVE = ROOT / "docs" / "CHANGELOG_AI.md"

NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
FIELDS = ("Changed", "Where", "Verified", "Open", "Affects", "Status doc")
STATUS_RE = re.compile(r"^(?:no change|pending: *\S.*|applied (\d{4}-\d{2}-\d{2}))$")
ARCHIVE_MARKER = "\n---\n"
# The forms a Where line may start with; anything after them is free text.
WHERE_RE = re.compile(r"^(?:main|local only|PR #\d+|branch|#\d+)\b")
# A Where line naming a PR or branch; on main that change is merged. "local only" is left alone.
UNMERGED_RE = re.compile(r"^(?:PR #\d+|branch|#\d+)\b")
ARCHIVE_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}):", re.MULTILINE)


@dataclass
class Entry:
    path: Path
    date: str
    text: str
    status: str
    where: str


def _field_lines(text: str) -> tuple[dict[str, str], list[str]]:
    """The first line of each '- Field:' bullet, by field name, and any field given twice."""
    out: dict[str, str] = {}
    repeated: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^- ([A-Za-z ]+): ?(.*)$", line)
        if m and m.group(1) in FIELDS:
            if m.group(1) in out:
                repeated.append(m.group(1))
            else:
                out[m.group(1)] = m.group(2).strip()
    return out, repeated


def parse(path: Path) -> tuple[Entry | None, list[str]]:
    """One entry file, or None and the reasons it is malformed."""
    errors: list[str] = []
    m = NAME_RE.match(path.name)
    if not m:
        return None, [f"{path.name}: name must be YYYY-MM-DD-short-name.md (lowercase, hyphens)"]
    date = m.group(1)
    if not _is_date(date):
        return None, [f"{path.name}: {date} is not a calendar date"]
    text = path.read_text(encoding="utf-8").strip() + "\n"
    lines = text.splitlines()
    if not lines[0].startswith(f"## {date}: "):
        errors.append(f"{path.name}: first line must be '## {date}: <change> (#PR)'")
    if sum(1 for line in lines if line.startswith("## ")) != 1:
        errors.append(f"{path.name}: one entry per file (exactly one '## ' heading)")
    fields, repeated = _field_lines(text)
    for name in repeated:
        errors.append(f"{path.name}: '- {name}:' appears more than once")
    for name in FIELDS:
        if not fields.get(name):
            errors.append(f"{path.name}: missing or empty '- {name}:' line")
    status = fields.get("Status doc", "")
    sm = STATUS_RE.match(status)
    if status and (not sm or (sm.group(1) and not _is_date(sm.group(1)))):
        errors.append(
            f"{path.name}: '- Status doc:' must be 'no change', 'pending: <the edits>' or "
            "'applied YYYY-MM-DD'"
        )
    where = fields.get("Where", "")
    if where and not WHERE_RE.match(where):
        errors.append(
            f"{path.name}: '- Where:' must start with 'main', 'local only', 'PR #N', 'branch' "
            "or '#N'"
        )
    if errors:
        return None, errors
    return Entry(path=path, date=date, text=text, status=status, where=fields["Where"]), []


def _is_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def todo(entry: Entry) -> list[str]:
    """What the status refresh on main still has to do for this entry."""
    out = []
    if entry.status.startswith("pending"):
        out.append("apply its Status doc edit")
    if UNMERGED_RE.match(entry.where):
        out.append("set Where to main")
    return out


def load(entry_dir: Path = ENTRY_DIR) -> tuple[list[Entry], list[str]]:
    """Every entry, newest first (date, then name, descending), and every format error."""
    entries: list[Entry] = []
    errors: list[str] = []
    for path in sorted(entry_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        entry, errs = parse(path)
        errors += errs
        if entry:
            entries.append(entry)
    entries.sort(key=lambda e: (e.date, e.path.name), reverse=True)
    return entries, errors


PREFACE = """# Baker AI changelog

One entry per meaningful change, newest first by date: the entry files in `docs/changelog/` and
the archive `docs/CHANGELOG_AI.md` (entries written before the per-PR rule), merged. How to add
an entry, and how `docs/PRODUCT_STATUS.md` is kept current, is in `docs/changelog/README.md`.
"""


def build(entry_dir: Path = ENTRY_DIR, archive: Path = ARCHIVE) -> str:
    """The whole log in one view: a preface, then every entry newest first by date.

    Entry files and archive entries are merged by date; on the same date the entry files come
    first. The archive's own preface describes the old workflow, so it is left out.
    """
    entries, errors = load(entry_dir)
    if errors:
        raise ValueError("\n".join(errors))
    text = archive.read_text(encoding="utf-8")
    _, sep, rest = text.partition(ARCHIVE_MARKER)
    if not sep:
        rest = text
    starts = [m.start() for m in ARCHIVE_HEADING_RE.finditer(rest)]
    archived = [
        (ARCHIVE_HEADING_RE.match(rest, s).group(1), rest[s:end])
        for s, end in zip(starts, starts[1:] + [len(rest)], strict=True)
    ]
    # Each list is already newest first; sorting on date alone is stable, so ties keep the files
    # ahead of the archive and each source's own order.
    merged = sorted(
        [(e.date, e.text) for e in entries] + archived, key=lambda d: d[0], reverse=True
    )
    parts = [PREFACE + ARCHIVE_MARKER] + [body for _, body in merged]
    return "\n".join(p.rstrip("\n") + "\n" for p in parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["check", "build", "pending"])
    ap.add_argument("--dir", type=Path, default=ENTRY_DIR)
    ap.add_argument("--out", type=Path, help="build: write here instead of stdout")
    args = ap.parse_args(argv)

    entries, errors = load(args.dir)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.command == "check":
        print(f"{len(entries)} changelog entries OK")
    elif args.command == "pending":
        for e in entries:
            if steps := todo(e):
                name = e.path.relative_to(ROOT) if e.path.is_relative_to(ROOT) else e.path
                print(f"{name}: {'; '.join(steps)}")
    else:
        out = build(args.dir)
        if args.out:
            args.out.write_text(out, encoding="utf-8")
        else:
            sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
