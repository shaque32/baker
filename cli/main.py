"""Baker command line. Everything runs offline against one case database.

    python -m cli init      --db case.db
    python -m cli import    --db case.db --report item1.xlsx [--source-id item1]
    python -m cli ufdr-check --package item1.ufdr --out <empty folder> [--sample 20]
    python -m cli govdoc    --db case.db --pdf affidavit.pdf
    python -m cli claims    --db case.db list
    python -m cli claims    --db case.db propose [--only <para id> ...]
    python -m cli claims    --db case.db add --id C01 --paragraph <para id> --type identity
                            --text "..." --by expert:<name>
    python -m cli claims    --db case.db set --id C01 --status accepted|edited|removed
                            [--text "..."] --by expert:<name>
    python -m cli stipulate --db case.db --device dev:item1 --person "Daniel Petrov"
                            --by expert:<name>
    python -m cli audit     --db case.db [--fake] [--ai-review] [--label-all]
    python -m cli evidence  --db case.db --id <evidence id> --status accepted|dismissed|open
                            --reason "..." --by expert:<name>
    python -m cli verdict   --db case.db --claim C01 (--confirm | --set unproven --note "...")
                            --by expert:<name>
    python -m cli report    --db case.db --out report.html
    python -m cli verify-log --db case.db
    python -m cli redecide  --db case.db --by expert:<name>
    python -m cli serve     [--cases <folder> | --db case.db] [--port 8765] [--expert "<name>"]
                            [--open]
    python -m cli model-check
    python -m cli encrypt   --db case.db --by expert:<name>
    python -m cli passphrase --db case.db --by expert:<name>
    python -m cli demo      [--port 8766] [--expert "<name>"] [--no-open] [--build-only]
                            [--from-case <case folder> | --scripted]

`redecide` re-runs the verdict rules on the last audit's stored evidence after expert review;
it calls no model. `serve` opens the expert's screen on http://127.0.0.1 only. Without --db it
works on a cases folder (--cases, else $BAKER_CASES, else ~/Baker/cases), where the expert
makes a case, imports its files, settles the claims and runs the audit in the background, all
in the browser. `model-check` says whether the configured local model is there, is the pinned
file (SHA-256) and fits in this computer's memory.

`audit` uses the product components. Until they are all built it names what is missing;
`--fake` runs the eval stand-ins instead, and the report then says it is a test run.
`--ai-review` adds the local AI reviewer pass, which only sorts evidence for the expert (rules
0.2.0) and costs one model call per supporting item, so it is off by default.
`audit` saves each claim as it finishes and prints its progress. If it stops part way, run it
again: the finished claims' model outputs are reused, not recomputed. Claims a failed core
check already contradicts are not sent to the model (their labels could not change the
verdict); `--label-all` labels them too.
`demo` resets the synthetic demo case (eval/demo.py) and opens it on its own port, from its own
cases folder (~/Baker/demo/cases, or $BAKER_DEMO/cases), so each demo starts clean in seconds
and a screen share shows no other case. `--from-case` saves a finished synthetic case01 audit
(a real local-model run) as the demo from then on; `--scripted` goes back to the scripted one.
`encrypt` encrypts a case made before encryption at rest (its database and the copies of its
files; core/casework/protect.py), or finishes one that was interrupted, and prints its recovery
key once. Nothing encrypts a case on its own. `passphrase` changes an encrypted case's
passphrase. Every command on an encrypted case asks for its passphrase (or recovery key) in the
terminal; it is never taken from an option or the environment.
`ufdr-check` compares what Baker imports from a UFDR with the package's own report.xml, record
by record, without touching any case (docs/ingest/ufdr.md, "Before calling it verified"). It
writes ufdr-check.md and .json, which hold no case content and can be sent back, and
ufdr-check-private.md, a sample of records to compare in Cellebrite Reader, which stays here.
`claims propose` asks the local model for claims on every paragraph that has none yet; they
are stored as 'proposed' until the expert accepts, edits or removes them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import pipeline
from core.audit._llm_json import CloudPaused, ModelUnavailable
from core.audit._local_model import ModelConfigError
from core.audit.invariants import InvariantViolation
from core.contracts import ClaimStatus, ClaimType, EvidenceStatus, Verdict, VerdictDecision
from core.db import CaseLocked, apply_schema, connect
from core.report.html import write_report
from core.review import actions, audit_log


def _ask(prompt: str) -> str:
    """A secret typed in the terminal, never echoed."""
    import getpass

    if not sys.stdin.isatty():
        raise SystemExit("this needs a passphrase typed in a terminal")
    return getpass.getpass(prompt)


def _unlock(path: Path) -> None:
    from core import encryption

    if not encryption.is_encrypted_case(path) or encryption.is_unlocked(path):
        return
    for _ in range(3):
        try:
            encryption.unlock(path, _ask(f"Passphrase or recovery key for {path}: "))
            return
        except encryption.WrongSecret as e:
            print(f"error: {e}", file=sys.stderr)
    raise SystemExit("the case stays locked")


def _open(path: Path, create: bool = False):  # -> sqlite3.Connection
    if not create and not path.exists():
        raise SystemExit(f"no case database at {path}; run `init` first")
    _unlock(path)
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
    from core.ingest.coverage import format_text, summary
    from core.ingest.pick import report_importer

    Importer = report_importer(a.report)  # noqa: N806 - a class

    src = Importer(source_id=a.source_id, date_order=a.date_order).import_source(a.report, conn)
    print(f"imported {src.file_name} as {src.id} ({src.fidelity.value}), sha256 {src.sha256}")
    cov = summary(conn, src.id)
    if cov is not None:
        print(format_text(cov))
    return 0


def cmd_ufdr_check(a: argparse.Namespace) -> int:
    from core.ingest import ufdr_check

    try:
        result = ufdr_check.run(a.package, a.sample, a.date_order)
        paths = ufdr_check.write(result, a.out)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    d = result.shareable
    print(f"Differences found: {d['differences']}")
    if result.import_error:
        print(f"Baker refused the package: {result.import_error}")
    print(f"shareable, no case content (read it before sending): {paths[0]}")
    print(f"  the same for a program: {paths[1]}")
    print(f"PRIVATE, keep on this computer: {paths[2]}")
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
    if a.action == "propose":
        return _propose(conn, a.only)
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


def _propose(conn, paragraph_ids: list[str] | None) -> int:  # noqa: ANN001
    from core.audit._llm_json import PromptMissingError
    from core.audit._local_model import ModelConfigError
    from core.claims import extract
    from core.claims.propose import load_paragraphs, propose_claims

    try:
        paragraphs = load_paragraphs(conn, paragraph_ids)
        extractor = extract.create(conn)
    except (ValueError, ModelConfigError, PromptMissingError) as e:
        print(f"claims propose: {e}", file=sys.stderr)
        return 2
    if not paragraphs:
        print("claims propose: no paragraphs; import the government document first")
        return 2
    r = propose_claims(conn, extractor, paragraphs)
    for c in r.claims:
        print(f"{c.id}\tproposed\t{c.claim_type.value}\t{c.paragraph_id}\t{c.text}")
    for d in r.drops:
        where = "whole answer" if d.index is None else f"item {d.index}"
        print(f"dropped {d.paragraph_id} ({where}): {d.reason}", file=sys.stderr)
    print(
        f"{len(r.claims)} claims proposed; {len(r.skipped)} paragraphs skipped (already have"
        f" claims); {len(r.drops)} proposals dropped. Accept, edit or remove each with"
        " `claims set`."
    )
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
        import functools

        from core.casework import cloud as cloud_policy
        from core.llm import cloud as cloud_llm

        load = functools.partial(cloud_llm.load_config, case_db=Path(a.db))
        choice = cloud_policy.choose(conn, load)  # the case's saved cloud choice, as on the screen
        print(f"audit: {choice.why}", file=sys.stderr)
        try:
            comps = pipeline.real_components(conn, ai_review=a.ai_review, cloud=choice)
        except pipeline.ComponentsMissing as e:
            print(f"audit: {e}. Use --fake for a test run.", file=sys.stderr)
            return 2
        except ModelConfigError as e:
            print(f"audit: {e}", file=sys.stderr)
            return 2
    comps.label_settled = a.label_all

    def progress(done: int, total: int, d: VerdictDecision) -> None:
        print(f"[{done}/{total}] {d.claim_id}: {d.verdict.value}", file=sys.stderr, flush=True)

    try:
        result = pipeline.run_audit(conn, comps, progress=progress)
    except CloudPaused as e:
        print(
            f"audit paused: {e}. No claim was labeled by another model. Run it again to retry the"
            " cloud model, or turn cloud AI off for this case and run it again to label the whole"
            " case locally.",
            file=sys.stderr,
        )
        return 1
    except (InvariantViolation, ModelUnavailable) as e:
        print(
            f"audit stopped before it finished, so none of its verdicts count: {e}. The model"
            " outputs of the claims it finished are kept; run it again to resume from them.",
            file=sys.stderr,
        )
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
    from core.casework.cases import Case
    from core.timeline.settings import from_case

    conn = _open(a.db)
    tl = from_case(Case(Path(a.db)).settings)  # the case's own timeline settings
    print(f"wrote {write_report(conn, a.out, tl)}")
    return 0


def cmd_verify_log(a: argparse.Namespace) -> int:
    ok = audit_log.verify_chain(_open(a.db))
    print("audit log hash chain verified" if ok else "audit log hash chain FAILED")
    return 0 if ok else 1


def cmd_redecide(a: argparse.Namespace) -> int:
    from core.review.redecide import redecide

    conn = _open(a.db)
    try:
        result = redecide(conn, a.by)
    except InvariantViolation as e:
        print(f"redecide stopped, nothing was stored: {e}", file=sys.stderr)
        return 1
    tally: dict[str, int] = {}
    for d in result.decisions:
        tally[d.verdict.value] = tally.get(d.verdict.value, 0) + 1
    print(f"{result.run_id} (rules only, evidence from {result.from_run}): {tally}")
    for cid, why in sorted(result.skipped.items()):
        print(f"  {cid}: {why}")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    from core.casework.cases import cases_home
    from ui.server import make_server, url

    home = None
    if a.db is not None:
        if not a.db.exists():
            raise SystemExit(f"no case database at {a.db}; run `init` first")
    else:
        home = a.cases or cases_home()
        home.mkdir(parents=True, exist_ok=True)
    try:
        server = make_server(a.db, a.port, a.expert, home=home)
    except OSError as e:
        raise SystemExit(f"cannot open port {a.port} on 127.0.0.1 ({e}); try --port 8766") from e
    where = f"case {a.db}" if a.db is not None else f"cases in {home}"
    print(f"Baker: {url(server)}  ({where}; this computer only; Ctrl+C stops it)")
    print("A running audit stops when this does; its finished claims are kept and resume later.")
    if a.open:
        import webbrowser

        webbrowser.open(url(server))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_encrypt(a: argparse.Namespace) -> int:
    from core.casework import protect
    from core.casework.cases import Case

    if not a.db.exists():
        raise SystemExit(f"no case database at {a.db}")
    case = Case(a.db)
    st = protect.state(case)
    if st == "encrypted":
        raise SystemExit(f"{a.db} is already encrypted")
    if st == "partial":
        print("This case's encryption did not finish; this finishes it.")
        secret, again = _ask("Passphrase chosen then, or the recovery key: "), None
    else:
        print("Encrypting the database and the copies of the case's files. This cannot be undone.")
        secret = _ask("New passphrase (at least 12 characters): ")
        again = _ask("The passphrase again: ")
    done = protect.encrypt_case(case, secret, a.by, again=again)
    print(f"encrypted {a.db}: database {'now' if done.database else 'already'} encrypted, "
          f"{done.files} copied file(s) encrypted")  # fmt: skip
    print()
    print(f"Recovery key: {done.recovery_key}")
    print("Write it down now and keep it away from this computer. It opens the case if the")
    print("passphrase is lost. Baker shows it only this once and keeps no copy.")
    return 0


def cmd_passphrase(a: argparse.Namespace) -> int:
    from core.casework import protect
    from core.casework.cases import Case

    current = _ask("Current passphrase or recovery key: ")
    new = _ask("New passphrase (at least 12 characters): ")
    again = _ask("The new passphrase again: ")
    protect.change_passphrase(Case(a.db), current, new, again, a.by)
    print("passphrase changed; the recovery key is the same as before")
    return 0


def cmd_model_check(a: argparse.Namespace) -> int:
    from core.casework.model_check import check_model

    result = check_model()
    for level, message in result.lines:
        print(f"{level:4}  {message}")
    print("model ready" if result.ok else "model NOT ready")
    return 0 if result.ok else 1


def cmd_demo(a: argparse.Namespace) -> int:
    from eval import demo

    root = demo.demo_root()
    if a.from_case is not None:
        snap = demo.save_snapshot(root, a.from_case)
        print(f"saved {a.from_case} as the demo; every reset restores it (copy in {snap})")
    elif a.scripted:
        demo.drop_snapshot(root)
    case, kind = demo.reset(root)
    what = "a saved audit" if kind == "snapshot" else "scripted labels, no model; see docs/demo.md"
    print(f"demo case ready: {case.name} ({what}): {demo.summary(case)}")
    if a.build_only:
        return 0
    return cmd_serve(
        argparse.Namespace(
            db=None, cases=demo.cases_dir(root), port=a.port, expert=a.expert, open=not a.no_open
        )
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="baker", description="Baker: audit claims about phone data.")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:  # noqa: ANN001
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--db", type=Path, required=True)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "create a case database")
    sp = add(
        "import",
        cmd_import,
        "import a phone report: Cellebrite (.xlsx, .pdf, .ufdr/.zip) or Magnet AXIOM (.xml, .xlsx)",
    )
    sp.add_argument("--report", type=Path, required=True)
    sp.add_argument("--source-id")
    sp.add_argument(
        "--date-order",
        choices=("mdy", "dmy"),
        help="the report's date order (month or day first), when the report does not decide it",
    )
    sp = sub.add_parser(
        "ufdr-check", help="check Baker's UFDR import against the package's own report.xml"
    )
    sp.set_defaults(fn=cmd_ufdr_check)
    sp.add_argument("--package", type=Path, required=True, help="the .ufdr (or .zip) file")
    sp.add_argument("--out", type=Path, required=True, help="an empty folder for the results")
    sp.add_argument("--sample", type=int, default=20, help="records per kind to compare in Reader")
    sp.add_argument("--date-order", choices=("mdy", "dmy"))
    sp = add("govdoc", cmd_govdoc, "import the government document (PDF)")
    sp.add_argument("--pdf", type=Path, required=True)

    sp = add("claims", cmd_claims, "list, add or review claims")
    sp.add_argument("action", choices=("list", "add", "set", "propose"))
    sp.add_argument("--id")
    sp.add_argument("--paragraph")
    sp.add_argument(
        "--only", action="append", help="propose: limit to this paragraph id (repeatable)"
    )
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
    sp.add_argument(
        "--ai-review",
        action="store_true",
        help="also run the local AI reviewer, a sorting aid that decides nothing",
    )
    sp.add_argument(
        "--label-all",
        action="store_true",
        help="also label claims a failed core check already contradicts (more model calls)",
    )

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

    sp = add("redecide", cmd_redecide, "re-run the verdict rules after expert review (no model)")
    sp.add_argument("--by", required=True)

    sp = add("encrypt", cmd_encrypt, "encrypt a case's database and copied files (one way)")
    sp.add_argument("--by", required=True)
    sp = add("passphrase", cmd_passphrase, "change an encrypted case's passphrase")
    sp.add_argument("--by", required=True)

    sp = sub.add_parser("serve", help="open the expert's screen on this computer")
    sp.set_defaults(fn=cmd_serve)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--db", type=Path, help="one case database")
    g.add_argument("--cases", type=Path, help="the cases folder (default ~/Baker/cases)")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--expert", help="your name, recorded with every decision")
    sp.add_argument("--open", action="store_true", help="open it in the default browser")
    sp = sub.add_parser("model-check", help="check the local model before a first audit")
    sp.set_defaults(fn=cmd_model_check)
    sp = sub.add_parser("demo", help="reset the synthetic demo case and open it")
    sp.set_defaults(fn=cmd_demo)
    sp.add_argument("--port", type=int, default=8766, help="default 8766, beside a real `serve`")
    sp.add_argument("--expert", help="the name recorded with decisions made during the demo")
    sp.add_argument("--no-open", action="store_true", help="do not open the browser")
    sp.add_argument("--build-only", action="store_true", help="reset the case, do not serve it")
    g = sp.add_mutually_exclusive_group()
    g.add_argument(
        "--from-case", type=Path, help="save this finished synthetic case01 audit as the demo"
    )
    g.add_argument("--scripted", action="store_true", help="forget a saved audit; use the script")
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.fn(a)
    except (actions.ReviewError, CaseLocked) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
