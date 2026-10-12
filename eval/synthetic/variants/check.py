"""Import every layout variant and check it against what a correct import gives back.

    python -m eval.synthetic.variants.check [--out DIR] [--only NAME ...]

For each variant: the records Baker imported match the synthetic phone exactly, or the coverage
summary reports what was not read (the codes the variant lists); every data row written is
either imported or reported skipped; and the summary's own words pass the forbidden-word check.
Exit status 1 if any variant fails. All data is synthetic.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from core.audit.invariants import FORBIDDEN_WORDS
from core.db import apply_schema
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.cellebrite_pdf import CellebritePdfImporter
from core.ingest.coverage import CoverageSummary, load, summarize
from eval.synthetic.variants.catalog import VARIANTS, Variant

SOURCE_ID = "variant"


@dataclass
class Result:
    variant: Variant
    problems: list[str] = field(default_factory=list)
    summary: CoverageSummary | None = None
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.problems


def _ws(s: str) -> str:
    return " ".join(s.split())


def _messages(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT m.body, m.ts_utc, a.identifier, m.direction FROM messages m"
        " LEFT JOIN accounts a ON a.id = m.sender_account_id"
    ).fetchall()


def _calls(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT c.ts_utc, fa.identifier, ta.identifier, c.direction, c.duration_s FROM calls c"
        " LEFT JOIN accounts fa ON fa.id = c.from_account_id"
        " LEFT JOIN accounts ta ON ta.id = c.to_account_id"
    ).fetchall()


def _diff(name: str, want: list, got: list) -> list[str]:
    w, g = Counter(want), Counter(got)
    if w == g:
        return []
    missing = list((w - g).elements())[:3]
    extra = list((g - w).elements())[:3]
    return [f"{name}: expected {len(want)}, got {len(got)}; missing {missing}; extra {extra}"]


def check_payload_accounting(payload: dict, written: dict[str, int]) -> list[str]:
    """Every row is imported or reported: per table, read = imported + skipped; per sheet
    written, every data row is accounted for in the table or in the not-imported list."""
    problems: list[str] = []
    tables = {t["name"]: t for t in payload.get("tables", [])}
    skipped_out = {n["name"]: n for n in payload.get("not_imported", [])}
    for t in tables.values():
        skipped = sum(t["rows_skipped"].values())
        if t["rows_read"] != t["rows_imported"] + skipped:
            problems.append(
                f"{t['name']}: read {t['rows_read']} != imported {t['rows_imported']}"
                f" + skipped {skipped}"
            )
    for sheet, n in written.items():
        if sheet == "Summary":
            continue
        if sheet in tables:
            t = tables[sheet]
            counted = t["rows_imported"] + sum(
                v for k, v in t["rows_skipped"].items() if k != "empty"
            )
            if counted != n:
                problems.append(f"{sheet}: wrote {n} data rows, coverage accounts for {counted}")
        elif sheet in skipped_out:
            if int(skipped_out[sheet].get("rows") or 0) < n:
                problems.append(f"{sheet}: not imported but its row count is missing or short")
        else:
            problems.append(f"{sheet}: neither imported nor listed as not imported")
    return problems


def run_variant(v: Variant, out: Path) -> Result:
    res = Result(v)
    built = v.build(out)
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    cls = CellebritePdfImporter if v.fmt == "pdf" else CellebriteExcelImporter
    t0 = time.perf_counter()
    cls(source_id=SOURCE_ID, **v.importer_kwargs).import_source(built.path, conn)  # type: ignore[arg-type]
    res.seconds = time.perf_counter() - t0
    cov = load(conn, SOURCE_ID)
    if cov is None:
        res.problems.append("no source_coverage row written")
        return res
    s = summarize(cov)
    res.summary = s
    e = v.expect

    got = _messages(conn)
    if e.messages is not None:
        want = e.messages
        if e.bodies_reflowed:
            want = [(_ws(b), *rest) for b, *rest in want]
            got = [(_ws(b), *rest) for b, *rest in got]
        res.problems += _diff("messages", want, got)
    if e.message_count is not None and len(got) != e.message_count:
        res.problems.append(f"messages: expected {e.message_count}, got {len(got)}")
    if e.calls is not None:
        res.problems += _diff("calls", e.calls, _calls(conn))
    if e.contacts is not None:
        n = conn.execute("SELECT count(*) FROM contacts").fetchone()[0]
        if n != e.contacts:
            res.problems.append(f"contacts: expected {e.contacts}, got {n}")
    if e.attachments is not None:
        files = [r[0] for r in conn.execute("SELECT file_name FROM attachments")]
        res.problems += _diff("attachments", e.attachments, files)

    if s.status != e.status:
        res.problems.append(
            f"status: expected {e.status}, got {s.status}: "
            + "; ".join(i.plain for i in s.attention)[:400]
        )
    codes = {i.code for i in s.items}
    att = {i.code for i in s.attention}
    for c in sorted(e.attention - att):
        res.problems.append(f"coverage should flag {c!r} for review")
    for c in sorted(e.info - codes):
        res.problems.append(f"coverage should note {c!r}")
    res.problems += check_payload_accounting(cov.payload, built.written)
    for i in s.items:
        own = "".join(t for t, quoted in i.parts if not quoted)
        m = FORBIDDEN_WORDS.search(own)
        if m:
            res.problems.append(f"summary says {m.group(0)!r} in its own words: {i.plain}")
    return res


def run(out: Path, only: list[str] | None = None) -> list[Result]:
    out.mkdir(parents=True, exist_ok=True)
    return [run_variant(v, out) for v in VARIANTS if not only or v.name in only]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="keep the built files here")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("-v", "--verbose", action="store_true", help="print every coverage item")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        results = run(a.out or Path(tmp), a.only)
    width = max(len(r.variant.name) for r in results)
    for r in results:
        mark = "ok  " if r.ok else "FAIL"
        status = r.summary.status if r.summary else "-"
        print(f"{mark} {r.variant.name:<{width}}  {status:<12} {r.seconds:6.2f}s  {r.variant.what}")
        for p in r.problems:
            print(f"       ! {p}")
        if a.verbose and r.summary:
            for i in r.summary.items:
                print(f"       {'*' if i.level == 'attention' else '-'} {i.plain}")
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} variants pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["Result", "check_payload_accounting", "run", "run_variant"]
