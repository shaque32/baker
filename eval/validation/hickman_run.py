"""The validation-v1 run on a public Hickman phone (eval/validation/PREREGISTERED.md).

    python -m eval.validation.hickman_run --ufdr PHONE.ufdr --claims CLAIMS.jsonl --out DIR

It builds one case the way an expert would, then runs `mabillon audit` with its defaults:
1. checks the claims file and the package's report.xml against the hashes it is given;
2. renders the claims as a numbered affidavit PDF (paragraph n is claim n's text, verbatim);
3. creates DIR/case.db in local mode, imports the UFDR, imports the affidavit, adds each claim
   to its paragraph, and sets the case up as the affidavit defines it: the phone is the TARGET
   PHONE, SUBJECT-1 used it (a stipulation), and each other SUBJECT-<n> the claims name is a
   person, with no stipulation or link;
4. runs the audit with the product's local components (no AI reviewer, no cloud);
5. writes DIR/report.html, DIR/run.json (versions, machine, times) and DIR/results.zip. If the
   report's own checks refuse it, run.json says why and the results go out without it.

The claims file holds claims only, never their answers: the run machine never sees the key.
Run it again with the same DIR to resume: a built case is kept, and the audit reuses the model
outputs of the claims it finished. --fake swaps in the eval's stand-in components (tests only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from core.contracts import ClaimType, DocKind
from core.db import apply_schema, connect

ACTOR = "expert:validation"
SOURCE_ID = "ios15"
OWNER = "SUBJECT-1"
PHONE_NAME = "TARGET PHONE"  # the affidavit's name for the phone
# The people the affidavit defines, found in the claims text by this rule alone (never from the
# answers): every SUBJECT-<n> written in a claim.
SUBJECT = re.compile(r"\bSUBJECT-\d+\b")
TITLE = "AFFIDAVIT (VALIDATION V1, HICKMAN PUBLIC IMAGE, NOT A REAL CASE)"
# The batch 3 writer typed "content" for content_meaning; ClaimType has no "content". The claim
# type only picks which checks run; the signed answers do not depend on it.
TYPE_ALIASES = {"content": "content_meaning"}
RESULT_FILES = ("case.db", "run.json", "report.html", "progress.log")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def report_xml_sha256(ufdr: Path) -> str:
    """The SHA-256 of the package's report.xml, streamed out of the zip."""
    from core.ingest.ufdr import find_report

    h = hashlib.sha256()
    with zipfile.ZipFile(ufdr) as z, z.open(find_report(z)) as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def load_claims(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if [r["para_no"] for r in rows] != list(range(1, len(rows) + 1)):
        raise SystemExit(f"{path}: paragraphs must run 1..n in order")
    if any("label" in r or "key_evidence" in r for r in rows):
        raise SystemExit(f"{path}: holds answers; the run machine gets claims only")
    for r in rows:
        r["claim_type"] = ClaimType(TYPE_ALIASES.get(r["claim_type"], r["claim_type"])).value
    return rows


def render_affidavit(claims: list[dict], path: Path) -> Path:
    """Claim n as printed paragraph n, laid out like the synthetic govdoc fixtures."""
    from eval.synthetic import govdocs as g

    paras = (g.Para(TITLE, heading=True),) + tuple(g.Para(c["text"], c["para_no"]) for c in claims)
    g._write(g._layout(paras, indent_style=False), path, TITLE)
    return path


def build(ufdr: Path, claims: list[dict], out: Path, log) -> None:  # noqa: ANN001
    from core.ingest.govdoc import PdfGovDocIngester
    from core.ingest.ufdr import UfdrImporter
    from core.review import actions

    db = out / "case.db"
    db.unlink(missing_ok=True)
    conn = connect(db)
    apply_schema(conn)
    t = time.monotonic()
    src = UfdrImporter(source_id=SOURCE_ID).import_source(ufdr, conn)
    log(f"imported {src.file_name} ({src.fidelity.value}) in {time.monotonic() - t:.0f} s")
    _, paragraphs = PdfGovDocIngester(DocKind.AFFIDAVIT).ingest(
        render_affidavit(claims, out / "affidavit.pdf"), conn
    )
    by_label = {p.label: p for p in paragraphs if p.label}
    for c in claims:
        para = by_label.get(str(c["para_no"]))
        if para is None:
            raise SystemExit(f"{c['claim_id']}: the ingester found no paragraph {c['para_no']}")
        kind = ClaimType(c["claim_type"])
        actions.add_claim(conn, c["claim_id"], para.id, c["text"], kind, ACTOR)
    actions.name_device(conn, f"dev:{SOURCE_ID}", [PHONE_NAME], ACTOR)
    actions.stipulate_device_owner(conn, f"dev:{SOURCE_ID}", OWNER, ACTOR)
    others = sorted(set(SUBJECT.findall(" ".join(c["text"] for c in claims))) - {OWNER})
    for name in others:
        actions.add_person(conn, name, ACTOR)
    conn.close()
    log(
        f"case built: {len(claims)} claims on {len(paragraphs)} paragraphs; the phone is"
        f" {PHONE_NAME}, used by {OWNER}; other people: {', '.join(others) or 'none'}"
    )


def machine() -> dict:
    info: dict = {"python": sys.version.split()[0], "platform": platform.platform()}
    smi = shutil.which("nvidia-smi")
    try:
        if smi is None:
            raise OSError("no nvidia-smi")
        info["gpu"] = subprocess.run(  # noqa: S603 - fixed arguments
            [smi, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        info["gpu"] = None
    try:
        import llama_cpp

        info["llama_cpp_python"] = llama_cpp.__version__
        info["gpu_offload"] = bool(llama_cpp.llama_supports_gpu_offload())
    except ImportError:
        info["llama_cpp_python"] = None
    return info


def audit(out: Path, fake: bool, log) -> dict:  # noqa: ANN001
    from core import pipeline

    conn = connect(out / "case.db")
    if fake:
        from eval.pipeline_fakes import fake_components

        comps = fake_components()
    else:
        comps = pipeline.real_components(conn)  # local model, no AI reviewer, no cloud

    def progress(done: int, total: int, d) -> None:  # noqa: ANN001
        log(f"[{done}/{total}] {d.claim_id}: {d.verdict.value}")

    t = time.monotonic()
    result = pipeline.run_audit(conn, comps, progress=progress)
    tally: dict[str, int] = {}
    for d in result.decisions:
        tally[d.verdict.value] = tally.get(d.verdict.value, 0) + 1
    calls = {
        purpose: {"calls": n, "first_utc": first, "last_utc": last}
        for purpose, n, first, last in conn.execute(
            "SELECT r.purpose, COUNT(*), MIN(c.at_utc), MAX(c.at_utc) FROM model_calls c"
            " JOIN model_runs r ON r.id = c.model_run_id GROUP BY r.purpose"
        )
    }
    conn.close()
    return {
        "run_id": result.run_id,
        "fake": result.fake,
        "verdicts": tally,
        "audit_seconds": round(time.monotonic() - t),
        "model_calls": calls,
        "model_outputs_reused": result.model_outputs_reused,
        "dropped_labels": result.dropped_labels,
        "unlabeled": result.unlabeled,
    }


def report(out: Path, log) -> dict:  # noqa: ANN001
    """Write report.html. A report the invariants refuse is left out and said so: the audit's
    results are in case.db either way, and the score is read from there."""
    from core.audit.invariants import InvariantViolation
    from core.report.html import write_report

    path = out / "report.html"
    path.unlink(missing_ok=True)  # never ship a report from an earlier attempt
    conn = connect(out / "case.db")
    try:
        write_report(conn, path)
    except InvariantViolation as e:
        log(f"report not written: {e}")
        return {"written": False, "error": str(e)}
    finally:
        conn.close()
    return {"written": True}


def model_config() -> dict | None:
    from core.audit._local_model import ModelConfigError, load_config

    try:
        cfg = load_config()
    except ModelConfigError:
        return None
    return {"name": cfg.name, "sha256": cfg.sha256, "n_ctx": cfg.n_ctx}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ufdr", type=Path, required=True)
    ap.add_argument("--claims", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--claims-sha256", help="refuse a claims file with another hash")
    ap.add_argument("--report-sha256", help="refuse a package whose report.xml has another hash")
    ap.add_argument("--fake", action="store_true", help="stand-in components (tests only)")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    plog = (a.out / "progress.log").open("a", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ} {msg}"
        print(line, flush=True)
        plog.write(line + "\n")
        plog.flush()

    from core import build as build_mod
    from core.audit.rules import RULE_VERSION

    run_path = a.out / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else {}
    claims_sha = sha256_file(a.claims)
    if a.claims_sha256 and claims_sha != a.claims_sha256:
        raise SystemExit(f"{a.claims}: SHA-256 {claims_sha}, expected {a.claims_sha256}")
    claims = load_claims(a.claims)
    built = a.out / "built.ok"  # the inputs the case in DIR was built from
    if built.exists():
        was = json.loads(built.read_text(encoding="utf-8"))
        if was["claims_sha256"] != claims_sha:
            raise SystemExit(
                f"{a.out} was built from claims {was['claims_sha256']}; use a new --out"
            )
        if a.report_sha256 and was["report_xml_sha256"] != a.report_sha256:
            raise SystemExit(
                f"{a.out} was built from report.xml {was['report_xml_sha256']}; use a new --out"
            )
    run.setdefault("started_utc", f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}")
    run.update(
        build=build_mod.build_info(),
        rule_version=RULE_VERSION,
        model=None if a.fake else model_config(),
        machine=machine(),
        claims={"file": a.claims.name, "sha256": claims_sha, "n": len(claims)},
    )
    if not built.exists():
        log("checking the phone package's report.xml")
        report_sha = report_xml_sha256(a.ufdr)
        if a.report_sha256 and report_sha != a.report_sha256:
            raise SystemExit(f"report.xml SHA-256 {report_sha}, expected {a.report_sha256}")
        run["report_xml_sha256"] = report_sha
        build(a.ufdr, claims, a.out, log)
        inputs = {"claims_sha256": claims_sha, "report_xml_sha256": report_sha}
        built.write_text(json.dumps(inputs), encoding="utf-8")
    run_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    from core.pipeline import ComponentsMissing

    try:
        run["audit"] = audit(a.out, a.fake, log)
    except ComponentsMissing as e:
        raise SystemExit(f"audit: {e}") from e
    run["finished_utc"] = f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"
    run["report"] = report(a.out, log)
    run_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    plog.close()
    with zipfile.ZipFile(a.out / "results.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for name in RESULT_FILES:
            if (a.out / name).exists():
                z.write(a.out / name, name)
    print(f"done: {run['audit']['verdicts']}; results in {a.out / 'results.zip'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
