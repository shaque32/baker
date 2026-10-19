"""The demo case: synthetic case01, audited and mostly reviewed, ready in seconds.

A real audit of case01 on a laptop takes hours, so a demo cannot wait for one. `baker demo`
builds this case instead, through the product's own code (case folder, read-only imports with
SHA-256, claims, owner stipulations, the audit with its real assumptions, retrieval, checks,
quote check and verdict rules, the expert actions and the hash-chained log). Two things are
scripted from the answer Arsh signed in eval/gold/case01/gold.jsonl, and the screen and the
report say so on every page:

- The evidence labels. ScriptedLabeler labels a claim's signed key evidence the way the gold
  verdict points (supports for supported and unproven claims, contradicts for contradicted
  ones) and every other retrieved record irrelevant. No model runs. On a real case the local
  model labels the evidence.
- The expert's review. The scripted expert accepts key evidence in the gold direction and
  dismisses the rest, giving the answer key's rationale as the reason, on every claim except
  LEFT_OPEN. Those wait for the person giving the demo (docs/demo.md says what to do on each).

Two additions that are not in the answer key:

- The demo claims in eval/demo_claims.jsonl. D01 is an absence claim read from paragraph 11 ("no
  WhatsApp messages March 20 to 23"). Nothing contradicts it, but Item 1 is a curated report,
  which cannot show that something is absent, so the absence check is inconclusive and the rules
  leave the claim unproven. It shows Baker declining to call silence an absence.
- `--paired` (build_scripted(paired=True)) also imports a UFDR of Item 1 that holds records the
  curated report left out (eval/synthetic/paired.py), so the Selection tab shows the paired
  selection audit: what the curated report holds against the larger source of the same phone.

Everything is synthetic. The demo lives in its own cases folder (~/Baker/demo/cases), so a
screen share never shows another case. `--from-case` saves a finished synthetic case01 audit (for
example a real local-model run) as the demo instead; reset then restores that copy.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from core import encryption, pipeline
from core.audit.invariants import record_text
from core.casework import cases
from core.contracts import (
    Assumption,
    ClaimType,
    EvidenceCandidate,
    EvidenceStatus,
    GoldClaim,
    ModelRun,
    Stance,
    StanceLabel,
)
from core.db import connect
from core.review import actions
from core.review.redecide import redecide

EVAL_DIR = Path(__file__).resolve().parent
GOLD = EVAL_DIR / "gold" / "case01" / "gold.jsonl"
SHEET = EVAL_DIR / "gold" / "case01" / "assumptions.jsonl"
DEMO_CLAIMS = EVAL_DIR / "demo_claims.jsonl"  # demo-only claims, not signed gold
CASE_META = EVAL_DIR / "synthetic" / "case01" / "case.json"

DEMO_ROOT_ENV = "BAKER_DEMO"
DEFAULT_DEMO_ROOT = Path.home() / "Baker" / "demo"
DEMO_FOLDER = "demo-case01"  # where a restored snapshot goes
DEMO_NAME = "Demo: Petrov and Reyes phones (synthetic case01)"
SETUP_ACTOR = "expert:Baker demo setup"
SCRIPTED_EXPERT = "expert:Demo expert (scripted from the answer key)"

# Claims the scripted expert leaves for the live demo: C05 goes SUPPORTED only when the person
# giving the demo accepts its message and re-runs the verdicts.
LEFT_OPEN = ("C05",)

# The answer key's rationales are not reused as reasons: they name what the tool must never
# say (the report withholds itself on such words). docs/demo.md explains each trap instead.
ACCEPT_REASON = "Scripted demo review: signed key evidence for this claim, read the same way."
DISMISS_REASON = (
    "Scripted demo review: the signed answer key does not rest this claim on this item."
)

DEMO_RUN = ModelRun(
    id="mr:demo-scripted-labels",
    purpose="stance",
    model_name="scripted demo labels (from the signed case01 answer key, no model)",
    model_sha256="0" * 64,
    prompt_version="none",
    params={"scripted_demo": True},
    seed=0,
    started_at_utc=datetime(2026, 10, 13, tzinfo=UTC),
)

_DIRECTION = {"supported": Stance.SUPPORTS, "contradicted": Stance.CONTRADICTS}

Clock = Callable[[], datetime]


def demo_root() -> Path:
    """<root>/cases is the cases folder the demo screen serves; <root>/snapshot is a saved case
    folder that reset restores instead of the scripted build."""
    env = os.environ.get(DEMO_ROOT_ENV, "").strip()
    return Path(env).expanduser() if env else DEFAULT_DEMO_ROOT


def cases_dir(root: Path) -> Path:
    return root / "cases"


def snapshot_dir(root: Path) -> Path:
    return root / "snapshot"


def load_demo_claims() -> list[dict]:
    """The demo-only claims (eval/demo_claims.jsonl), each with its one assumption."""
    return [
        json.loads(line)
        for line in DEMO_CLAIMS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_gold() -> dict[str, GoldClaim]:
    rows = [
        GoldClaim.model_validate_json(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {g.claim_id: g for g in rows}


class ScriptedLabeler:
    """StanceLabeler for the demo: key evidence in the answer key's direction, the rest
    irrelevant. Quotes the record's whole citable text, so the real quote check runs."""

    model_runs = (DEMO_RUN,)

    def __init__(self, conn: sqlite3.Connection, gold: dict[str, GoldClaim]) -> None:
        self.conn = conn
        self.gold = gold

    def label(self, assumption: Assumption, candidate: EvidenceCandidate) -> StanceLabel:
        text = record_text(self.conn, candidate.record_id)
        if not text:
            raise LookupError(f"{candidate.record_id} has no citable text")
        g = self.gold.get(assumption.claim_id)
        if g is not None and candidate.record_id in g.key_evidence:
            stance = _DIRECTION.get(g.gold_verdict.value, Stance.SUPPORTS)
            why = "Demo label, scripted from the answer key: key evidence for this claim."
        else:
            stance = Stance.IRRELEVANT
            why = "Demo label, scripted from the answer key: not key evidence for this claim."
        return StanceLabel(
            assumption_id=assumption.id,
            record_id=candidate.record_id,
            stance=stance,
            quote=text,
            rationale=why,
            model_run_id=DEMO_RUN.id,
        )


# ---------------------------------------------------------------- building the case


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _import(case: cases.Case, conn: sqlite3.Connection, path: Path, kind: str) -> None:
    """Import one file the way the screen does: copy into inputs/, hash, import read-only."""
    upload = cases.upload_path(case)
    shutil.copyfile(path, upload)
    cases.import_upload(case, conn, upload, _sha256(upload), path.name, kind, SETUP_ACTOR)


def _paragraph(conn: sqlite3.Connection, claim_id: str, para_no: int, page: int) -> str:
    rows = conn.execute(
        "SELECT id, page FROM govdoc_paragraphs WHERE label = ? ORDER BY page, para_no",
        (str(para_no),),
    ).fetchall()
    on_page = [r for r in rows if r[1] == page]
    if not (on_page or rows):
        raise SystemExit(f"demo: no paragraph printed as {para_no} for {claim_id}")
    return (on_page or rows)[0][0]


def _components(conn: sqlite3.Connection, gold: dict[str, GoldClaim]) -> pipeline.Components:
    from eval.pipeline_fakes import FakeReviewer
    from eval.run_pipeline import spec_filler

    signed, extra = spec_filler(SHEET, conn), spec_filler(DEMO_CLAIMS, conn)
    comps = pipeline.real_components(
        conn,
        replace={"labeler": ScriptedLabeler(conn, gold), "reviewer": FakeReviewer(False)},
        filler=lambda claim, allowed: signed(claim, allowed) or extra(claim, allowed),
    )
    comps.reviewable = lambda item: False  # no AI reviewer in the demo: the expert decides
    comps.model_runs = (*comps.model_runs, DEMO_RUN)
    return comps


def _scripted_review(conn: sqlite3.Connection, gold: dict[str, GoldClaim], run: dict) -> int:
    decided = 0
    for claim_id, items in sorted(run["manifest"].items()):
        g = gold.get(claim_id)
        if g is None or claim_id in LEFT_OPEN:
            continue
        want = _DIRECTION.get(g.gold_verdict.value)
        for e in pipeline.load_evidence(conn, items["evidence"]):
            if e.stance is Stance.IRRELEVANT:
                continue
            accept = want is not None and e.stance is want and e.record_id in g.key_evidence
            actions.decide_evidence(
                conn,
                e.id,
                EvidenceStatus.ACCEPTED if accept else EvidenceStatus.DISMISSED,
                SCRIPTED_EXPERT,
                ACCEPT_REASON if accept else DISMISS_REASON,
            )
            decided += 1
    return decided


def build_scripted(home: Path, paired: bool = False) -> cases.Case:
    """Build the scripted demo case as a new case folder in home. With paired, the case also
    holds a UFDR of Item 1 with records the curated report left out, imported after the audit
    so the verdicts are the same as without it."""
    from eval.run_pipeline import render_affidavit_pdf
    from eval.synthetic import paired as planted
    from eval.synthetic.generate import generate

    meta = json.loads(CASE_META.read_text(encoding="utf-8"))
    gold = load_gold()
    with tempfile.TemporaryDirectory(prefix="baker-demo-") as tmp:
        work = Path(tmp)
        generate(work / "reports", None)
        for s in meta["sources"]:
            got = _sha256(work / "reports" / s["file"])
            if got != s["sha256"]:
                raise SystemExit(f"demo: {s['file']} built with SHA-256 {got}, not {s['sha256']}")
        affidavit = render_affidavit_pdf("case01", work / "affidavit-case01-synthetic.pdf")

        case = cases.create_case(home, DEMO_NAME, SETUP_ACTOR)
        conn = connect(case.db)
        try:
            _import(case, conn, affidavit, "govdoc")
            for s in meta["sources"]:
                _import(case, conn, work / "reports" / s["file"], "report")
            for g in gold.values():
                para = _paragraph(conn, g.claim_id, g.para_no, g.page)
                actions.add_claim(
                    conn, g.claim_id, para, g.text, ClaimType(g.claim_type), SETUP_ACTOR
                )
            for d in load_demo_claims():
                para = _paragraph(conn, d["claim_id"], d["para_no"], d["page"])
                actions.add_claim(
                    conn, d["claim_id"], para, d["text"], ClaimType(d["claim_type"]), SETUP_ACTOR
                )
            for d in meta["devices"]:
                actions.stipulate_device_owner(
                    conn, f"dev:{d['source_id']}", d["owner"], SETUP_ACTOR
                )
            pipeline.run_audit(conn, _components(conn, gold), config={"demo": "scripted"})
            run = pipeline.last_run(conn)
            if run is None:
                raise SystemExit("demo: the scripted audit did not finish")
            _scripted_review(conn, gold, run)
            redecide(conn, SETUP_ACTOR)
            if paired:
                full = planted.write(work / "paired")["item1-full.ufdr"]
                _import(case, conn, full, "report")
        finally:
            conn.close()
    case.save_settings(demo="scripted", left_open=list(LEFT_OPEN), paired=paired)
    return case


# ---------------------------------------------------------------- reset and snapshot


def _writable(path: Path) -> None:
    for p in [path, *path.rglob("*")]:
        try:
            p.chmod(p.stat().st_mode | stat.S_IWUSR)
        except OSError:
            pass


def _remove(folder: Path) -> None:
    """Delete a demo folder. Inputs are read-only, so make them writable first (Windows)."""
    if folder.exists():
        _writable(folder)
        shutil.rmtree(folder)


def _is_demo(folder: Path) -> bool:
    try:
        settings = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(settings, dict) and bool(settings.get("demo"))


def check_synthetic(folder: Path) -> None:
    """Refuse any case that is not synthetic case01: a demo never shows real discovery.
    Every imported report must be one of case01's generated files (SHA-256 from case.json)
    and the government document must be the synthetic affidavit."""
    meta = json.loads(CASE_META.read_text(encoding="utf-8"))
    known = {s["sha256"] for s in meta["sources"]}
    db = folder / cases.DB_NAME
    if not db.is_file():
        raise SystemExit(f"demo: no case database in {folder}")
    if encryption.is_encrypted_case(db):
        raise SystemExit(
            "demo: that case is encrypted; save the demo from a synthetic case01 audit that is "
            "not (the demo case is shown on screen shares and opens without a passphrase)"
        )
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        reports = conn.execute("SELECT file_name, sha256 FROM sources WHERE kind != 'govdoc'")
        unknown = [name for name, sha in reports if sha not in known]
        titles = [t for (t,) in conn.execute("SELECT text FROM govdoc_paragraphs LIMIT 3")]
    finally:
        conn.close()
    if unknown:
        raise SystemExit(
            f"demo: {', '.join(unknown)} is not one of synthetic case01's reports; only a "
            "synthetic case01 audit can become the demo"
        )
    if not any("SYNTHETIC" in t.upper() for t in titles):
        raise SystemExit("demo: the government document is not the synthetic case01 affidavit")


def save_snapshot(root: Path, source: Path) -> Path:
    """Copy a finished synthetic case01 case folder to the snapshot; reset restores it."""
    source = source.expanduser().resolve()
    if source.name == cases.DB_NAME:
        source = source.parent
    check_synthetic(source)
    conn = sqlite3.connect(f"file:{source / cases.DB_NAME}?mode=ro", uri=True)
    try:
        done = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status = 'completed'"
        ).fetchone()[0]
    finally:
        conn.close()
    if not done:
        raise SystemExit("demo: that case has no finished audit yet; save it once the run is done")
    target = snapshot_dir(root)
    _remove(target)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*-wal", "*-shm", ".upload-*"))
    settings = json.loads((target / "case.json").read_text(encoding="utf-8") or "{}")
    settings.update(demo="snapshot", snapshot_of=str(source))
    (target / "case.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return target


def drop_snapshot(root: Path) -> None:
    _remove(snapshot_dir(root))


def reset(root: Path, paired: bool = False) -> tuple[cases.Case, str]:
    """Replace the demo case with a clean copy: the saved snapshot if there is one, else the
    scripted build. With paired, always the scripted build with Item 1's UFDR added (a saved
    snapshot is kept for the next plain reset). Returns the case and which one it is. Only demo
    cases are deleted; any other case folder in the demo's cases folder is left alone and stops
    the reset."""
    home = cases_dir(root)
    home.mkdir(parents=True, exist_ok=True)
    others = [c.folder.name for c in cases.list_cases(home) if not _is_demo(c.folder)]
    if others:
        raise SystemExit(
            f"demo: {home} holds cases that are not demo cases ({', '.join(others)}); the demo "
            "keeps its own folder so a screen share never shows another case"
        )
    for c in cases.list_cases(home):
        _remove(c.folder)
    if paired:
        return build_scripted(home, paired=True), "scripted-paired"
    snap = snapshot_dir(root)
    if (snap / cases.DB_NAME).is_file():
        folder = home / DEMO_FOLDER
        shutil.copytree(snap, folder)
        return cases.Case(folder / cases.DB_NAME), "snapshot"
    return build_scripted(home), "scripted"


def summary(case: cases.Case) -> dict[str, int]:
    conn = connect(case.db)
    try:
        return {
            label: n
            for label, n in conn.execute(
                "SELECT v.verdict, COUNT(*) FROM verdicts v WHERE v.pipeline_run_id = ("
                " SELECT id FROM pipeline_runs WHERE status = 'completed'"
                " ORDER BY started_at_utc DESC, id DESC LIMIT 1) GROUP BY v.verdict"
            )
        }
    finally:
        conn.close()
