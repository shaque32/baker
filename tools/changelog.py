"""The AI changelog: one entry file per PR in docs/changelog/, read as one log.

Each PR adds its own file instead of editing a shared one, so open PRs stop conflicting with
each other after every merge. docs/changelog/README.md gives the format.

    python tools/changelog.py check      # every entry file is well formed (run by the tests)
    python tools/changelog.py build      # the whole log, newest first, entry files then archive
    python tools/changelog.py pending    # entries whose PRODUCT_STATUS edit is not applied yet
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY_DIR = ROOT / "docs" / "changelog"
ARCHIVE = ROOT / "docs" / "CHANGELOG_AI.md"

NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
FIELDS = ("Changed", "Where", "Verified", "Open", "Affects", "Status doc")
STATUS_RE = re.compile(r"^(no change|pending|applied \d{4}-\d{2}-\d{2})\b")
ARCHIVE_MARKER = "\n---\n"


@dataclass
class Entry:
    path: Path
    date: str
    text: str
    status: str


def _field_lines(text: str) -> dict[str, str]:
    """The first line of each '- Field:' bullet, by field name."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^- ([A-Za-z ]+): ?(.*)$", line)
        if m and m.group(1) in FIELDS and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()
    return out


def parse(path: Path) -> tuple[Entry | None, list[str]]:
    """One entry file, or None and the reasons it is malformed."""
    errors: list[str] = []
    m = NAME_RE.match(path.name)
    if not m:
        return None, [f"{path.name}: name must be YYYY-MM-DD-short-name.md (lowercase, hyphens)"]
    date = m.group(1)
    text = path.read_text(encoding="utf-8").strip() + "\n"
    lines = text.splitlines()
    if not lines[0].startswith(f"## {date}: "):
        errors.append(f"{path.name}: first line must be '## {date}: <change> (#PR)'")
    if sum(1 for line in lines if line.startswith("## ")) != 1:
        errors.append(f"{path.name}: one entry per file (exactly one '## ' heading)")
    fields = _field_lines(text)
    for name in FIELDS:
        if not fields.get(name):
            errors.append(f"{path.name}: missing or empty '- {name}:' line")
    status = fields.get("Status doc", "")
    if status and not STATUS_RE.match(status):
        errors.append(
            f"{path.name}: '- Status doc:' must start with 'no change', 'pending' or "
            "'applied YYYY-MM-DD'"
        )
    if errors:
        return None, errors
    return Entry(path=path, date=date, text=text, status=status), []


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


def build(entry_dir: Path = ENTRY_DIR, archive: Path = ARCHIVE) -> str:
    """The whole log in one view: the archive's preface, the entry files, the archive's entries."""
    entries, errors = load(entry_dir)
    if errors:
        raise ValueError("\n".join(errors))
    text = archive.read_text(encoding="utf-8")
    head, sep, rest = text.partition(ARCHIVE_MARKER)
    if not sep:
        head, rest = "", text
    parts = [head.rstrip() + "\n" + ARCHIVE_MARKER] if head else []
    parts += [e.text for e in entries]
    parts.append(rest.lstrip("\n"))
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
            if e.status.startswith("pending"):
                print(e.path.relative_to(ROOT) if e.path.is_relative_to(ROOT) else e.path)
    else:
        out = build(args.dir)
        if args.out:
            args.out.write_text(out, encoding="utf-8")
        else:
            sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
