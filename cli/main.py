"""Baker command line. Everything runs offline against one case database.

    python -m cli init      --db case.db
    python -m cli import    --db case.db --report item1.xlsx [--source-id item1]
    python -m cli govdoc    --db case.db --pdf affidavit.pdf
    python -m cli claims    --db case.db list
    python -m cli claims    --db case.db add --id C01 --paragraph <para id> --type identity
                            --text "..." --by expert:<name>
    python -m cli claims    --db case.db set --id C01 --status accepted|edited|removed
                            [--text "..."] --by expert:<name>
    python -m cli stipulate --db case.db --device dev:item1 --person "Daniel Petrov"
                            --by expert:<name>
    python -m cli audit     --db case.db [--fake]
    python -m cli evidence  --db case.db --id <evidence id> --status accepted|dismissed|open
                            --reason "..." --by expert:<name>
    python -m cli verdict   --db case.db --claim C01 (--confirm | --set unproven --note "...")
                            --by expert:<name>
    python -m cli report    --db case.db --out report.html
    python -m cli verify-log --db case.db

`audit` uses the product components. Until they are all built it names what is missing;
`--fake` runs the eval stand-ins instead, and the report then says it is a test run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import pipeline
from core.audit.invariants import InvariantViolation
from core.contracts import ClaimStatus, ClaimType, EvidenceStatus, Verdict
from core.db import apply_schema, connect
from core.report.html import write_report
from core.review import actions, audit_log


def _open(path: Path, create: bool = False):  # -> sqlite3.Connection
    if not create and not path.exists():
        raise SystemExit(f"no case database at {path}; run `init` first")
    return connect(path)


def cmd_init(a: argparse.Namespace) -> int:
    if a.db.exists():
        raise SystemExit(f"{a.db} already exists")
    conn = _open(a.db, create=True)
    apply_schema(conn)
    print(f"created {a.db}")
    return 0


def cmd_import(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    if a.report.suffix.lower() == ".pdf":
        from core.ingest.cellebrite_pdf import CellebritePdfImporter as Importer
    else:
        from core.ingest.cellebrite_excel import CellebriteExcelImporter as Importer
    src = Importer(source_id=a.source_id).import_source(a.report, conn)
    print(f"imported {src.file_name} as {src.id} ({src.fidelity.value}), sha256 {src.sha256}")
    return 0


def cmd_govdoc(a: argparse.Namespace) -> int:
    from core.ingest.govdoc import PdfGovDocIngester

    conn = _open(a.db)
    doc, paras = PdfGovDocIngester().ingest(a.pdf, conn)
    print(f"imported {doc.title!r} as {doc.id}: {len(paras)} paragraphs")
    for p in paras:
        print(f"  {p.id}  page {p.page}  para {p.label or '#' + str(p.para_no)}")
    return 0


def cmd_claims(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    if a.action == "list":
        for c in pipeline.load_claims(conn, include_removed=True):
            print(f"{c.id}\t{c.status.value}\t{c.claim_type.value}\t{c.paragraph_id}\t{c.text}")
    elif a.action == "add":
        actions.add_claim(conn, a.id, a.paragraph, a.text, ClaimType(a.type), a.by)
        print(f"added {a.id}")
    else:
        actions.set_claim_status(conn, a.id, ClaimStatus(a.status), a.by, a.text)
        print(f"{a.id} is {a.status}")
    return 0


def cmd_stipulate(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    sid = actions.stipulate_device_owner(conn, a.device, a.person, a.by)
    print(f"recorded {sid}; every report lists it as a limitation")
    return 0


def cmd_audit(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    if a.fake:
        from eval.pipeline_fakes import fake_components

        comps = fake_components()
    else:
        try:
            comps = pipeline.real_components(conn)
        except pipeline.ComponentsMissing as e:
            print(f"audit: {e}. Use --fake for a test run.", file=sys.stderr)
            return 2
    try:
        result = pipeline.run_audit(conn, comps)
    except InvariantViolation as e:
        print(f"audit stopped, nothing was stored: {e}", file=sys.stderr)
        return 1
    tally: dict[str, int] = {}
    for d in result.decisions:
        tally[d.verdict.value] = tally.get(d.verdict.value, 0) + 1
    print(f"{result.run_id}{' (TEST RUN, stand-in components)' if result.fake else ''}: {tally}")
    return 0


def cmd_evidence(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    d = actions.decide_evidence(conn, a.id, EvidenceStatus(a.status), a.by, a.reason)
    print(f"recorded {d.id}; re-run the audit to update verdicts")
    return 0


def cmd_verdict(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    if a.confirm:
        actions.confirm_verdict(conn, a.claim, a.by, a.note or "")
    else:
        actions.override_verdict(conn, a.claim, Verdict(a.set), a.by, a.note or "")
    print(f"recorded the expert decision on {a.claim}")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    conn = _open(a.db)
    print(f"wrote {write_report(conn, a.out)}")
    return 0


def cmd_verify_log(a: argparse.Namespace) -> int:
    ok = audit_log.verify_chain(_open(a.db))
    print("audit log hash chain verified" if ok else "audit log hash chain FAILED")
    return 0 if ok else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="baker", description="Baker: audit claims about phone data.")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:  # noqa: ANN001
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--db", type=Path, required=True)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "create a case database")
    sp = add("import", cmd_import, "import a Cellebrite report (.xlsx or .pdf)")
    sp.add_argument("--report", type=Path, required=True)
    sp.add_argument("--source-id")
    sp = add("govdoc", cmd_govdoc, "import the government document (PDF)")
    sp.add_argument("--pdf", type=Path, required=True)

    sp = add("claims", cmd_claims, "list, add or review claims")
    sp.add_argument("action", choices=("list", "add", "set"))
    sp.add_argument("--id")
    sp.add_argument("--paragraph")
    sp.add_argument("--type", choices=[t.value for t in ClaimType])
    sp.add_argument("--text")
    sp.add_argument("--status", choices=("accepted", "edited", "removed"))
    sp.add_argument("--by")

    sp = add("stipulate", cmd_stipulate, "stipulate who used a device")
    sp.add_argument("--device", required=True)
    sp.add_argument("--person", required=True)
    sp.add_argument("--by", required=True)

    sp = add("audit", cmd_audit, "run the audit pipeline")
    sp.add_argument("--fake", action="store_true", help="test run with eval stand-ins")

    sp = add("evidence", cmd_evidence, "accept, dismiss or reopen an evidence item")
    sp.add_argument("--id", required=True)
    sp.add_argument("--status", choices=("accepted", "dismissed", "open"), required=True)
    sp.add_argument("--reason", required=True)
    sp.add_argument("--by", required=True)

    sp = add("verdict", cmd_verdict, "confirm or override a verdict")
    sp.add_argument("--claim", required=True)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--confirm", action="store_true")
    g.add_argument("--set", choices=[v.value for v in Verdict])
    sp.add_argument("--note")
    sp.add_argument("--by", required=True)

    sp = add("report", cmd_report, "write the HTML claims report")
    sp.add_argument("--out", type=Path, required=True)
    add("verify-log", cmd_verify_log, "verify the audit log hash chain")
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.fn(a)
    except actions.ReviewError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
