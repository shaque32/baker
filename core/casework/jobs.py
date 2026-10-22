"""Background work started from the review screen: the audit, claim proposal, the model check.

One job at a time per screen. A job runs in its own thread with its own database connection, so
the screen stays usable: the expert can review finished claims while the audit labels the rest
(core/pipeline.py writes each claim in one short transaction after its model work, and keeps
run_claims current for the progress page).

The audit job:
- runs the model check first (core/casework/model_check.py) and stops with its plain message if
  the model is missing, is not the pinned file, or does not fit in memory;
- runs the claims in the expert's order and keeps the computer awake (core/casework/awake.py);
- stops between claims when the expert presses Stop (the run is stored as stopped);
- on a later start, resumes: claims finished before reuse their stored model outputs.

Time estimates are rough and say so: model calls per claim from synthetic case01 times the
seconds per call measured on this computer (stored in ~/.baker/speed.json after each audit), or,
before any measurement, the 43 s per call measured on a 24 GB Mac with the 14B model.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core import pipeline
from core.audit._llm_json import CloudPaused, ModelUnavailable
from core.audit._local_model import ModelConfigError
from core.audit.invariants import InvariantViolation
from core.casework.awake import keep_awake
from core.casework.model_check import ModelCheck
from core.db import connect
from core.review.actions import ReviewError
from core.support import errors as support_errors

DEFAULT_SECONDS_PER_CALL = 43.0  # Qwen3-14B Q4 on a 24 GB Mac (Wave 3, PR #28)
# Opus 5.5 at medium effort on case01: 493 calls in 1,558 s (cloud bench 2026-10-14c).
CLOUD_SECONDS_PER_CALL = 3.2
CALLS_PER_CLAIM = 25  # synthetic case01 after PR #29: 495 model calls for 20 claims
LOCAL_CALLS_PER_CLAIM = 1  # assumption filling, which stays local in a cloud case
SPEED_FILE = Path.home() / ".baker" / "speed.json"
MIN_CALLS_TO_MEASURE = 5

ComponentsFor = Callable[..., pipeline.Components]  # (conn, ai_review) -> Components
ExtractorFor = Callable[..., object]  # (conn) -> LocalClaimExtractor
ModelCheckFn = Callable[..., ModelCheck]  # (progress=...) -> ModelCheck


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Job:
    kind: str  # audit | propose | model_check
    db: Path
    started_at: datetime = field(default_factory=_now)
    state: str = "running"  # running | done | failed | stopped
    message: str = ""
    done: int = 0
    total: int = 0
    awake: str = ""
    estimate_seconds: float | None = None  # the upfront estimate, kept for the progress page
    finished_at: datetime | None = None
    check: ModelCheck | None = None
    hashed: tuple[int, int] | None = None  # model check: bytes hashed of total
    components: pipeline.Components | None = None
    cloud: bool = False  # an audit whose stance labels come from the cloud model
    stop: threading.Event = field(default_factory=threading.Event)

    @property
    def running(self) -> bool:
        return self.state == "running"

    def end(self, state: str, message: str) -> None:
        self.message = message
        self.finished_at = _now()
        self.state = state

    def seconds_per_call(self) -> float | None:
        """Mean seconds per new model call in this job so far, once a few calls are made."""
        comps = self.components  # read once: a finished cloud job drops it
        return None if comps is None else measured_seconds(comps)


class Jobs:
    """At most one running job. The last job stays readable after it ends."""

    def __init__(self) -> None:
        self.current: Job | None = None
        self._lock = threading.Lock()

    def busy(self) -> bool:
        return self.current is not None and self.current.running

    def start(self, job: Job, target: Callable[[Job], None]) -> Job:
        with self._lock:
            if self.busy():
                raise ReviewError(f"wait for the {_KIND[self.current.kind]} to finish")  # type: ignore[union-attr]
            self.current = job

        def run() -> None:
            try:
                target(job)
            except BaseException as e:  # noqa: BLE001 - a job never takes the screen down
                support_errors.note(job.kind, e)  # type and Baker frames only, for a bug report
                if job.running:
                    job.end("failed", f"Stopped on an unexpected error ({type(e).__name__}: {e}).")
            finally:
                if job.running:
                    job.end("done", job.message or "Finished.")

        threading.Thread(target=run, name=f"baker-{job.kind}", daemon=True).start()
        return job


_KIND = {"audit": "audit", "propose": "claim proposal", "model_check": "model check"}


# ---------------------------------------------------------------- estimates


def _new_call_seconds(c: pipeline.Components, local_only: bool = False) -> list[float]:
    ports = {
        id(p): p for p in (getattr(x, "model", None) for x in (c.labeler, c.reviewer, *c.recorders))
    }
    return [
        float(getattr(s, "seconds", 0.0))
        for p in ports.values()
        if isinstance(getattr(p, "stats", None), list)
        for s in p.stats
        if not getattr(s, "reused", False)
        and (not local_only or getattr(s, "where", "local") == "local")
    ]


def measured_seconds(c: pipeline.Components) -> float | None:
    """Mean seconds per new model call so far, once there are enough calls to say."""
    secs = _new_call_seconds(c)
    return sum(secs) / len(secs) if len(secs) >= MIN_CALLS_TO_MEASURE else None


def seconds_per_call(speed_file: Path = SPEED_FILE) -> tuple[float, str]:
    """(seconds per model call, where the number comes from)."""
    try:
        data = json.loads(speed_file.read_text(encoding="utf-8"))
        spc = float(data["seconds_per_call"])
        if spc > 0:
            return spc, (
                f"measured on this computer ({data.get('calls', '?')} calls, "
                f"{str(data.get('measured_at_utc', ''))[:10]})"
            )
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return DEFAULT_SECONDS_PER_CALL, "measured on a 24 GB Mac with the 14B model; not this computer"


def record_speed(c: pipeline.Components, speed_file: Path = SPEED_FILE) -> None:
    """The local model's measured speed, for later estimates. Cloud calls are not counted."""
    secs = _new_call_seconds(c, local_only=True)
    if len(secs) < MIN_CALLS_TO_MEASURE:
        return
    try:
        speed_file.parent.mkdir(parents=True, exist_ok=True)
        speed_file.write_text(
            json.dumps(
                {
                    "seconds_per_call": round(sum(secs) / len(secs), 2),
                    "calls": len(secs),
                    "measured_at_utc": _now().isoformat().replace("+00:00", "Z"),
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def estimate_seconds(claims: int, spc: float, cloud_spc: float | None = None) -> float:
    """spc is the local model's seconds per call. With cloud_spc, stance calls run at the cloud
    rate and assumption filling stays on the local model."""
    if cloud_spc is None:
        return claims * CALLS_PER_CLAIM * spc
    stance_calls = CALLS_PER_CLAIM - LOCAL_CALLS_PER_CLAIM
    return claims * (LOCAL_CALLS_PER_CLAIM * spc + stance_calls * cloud_spc)


def duration(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"about {minutes} min"
    h, m = divmod(minutes, 60)
    return f"about {h} h {m:02d} min"


# ---------------------------------------------------------------- jobs


def _open(db: Path):  # -> sqlite3.Connection
    conn = connect(db)
    conn.execute("PRAGMA busy_timeout = 30000")  # the screen may be saving a decision
    return conn


def audit_job(
    *,
    actor: str,
    order: Sequence[str],
    components_for: ComponentsFor,
    model_check: ModelCheckFn | None,
    ai_review: bool = False,
    label_all: bool = False,
    cloud_opt_in: bool = False,
) -> Callable[[Job], None]:
    """cloud_opt_in: the case's stance labels come from the cloud model. The local model check
    still gates the start: assumption filling (and the AI reviewer) run on the local model."""

    def run(job: Job) -> None:
        conn = _open(job.db)
        try:
            pipeline.mark_stale_runs_stopped(conn)
            job.total = len(order)
            if model_check is not None:
                job.message = "Checking the model."

                def hashed(done: int, total: int) -> None:
                    job.hashed = (done, total)

                job.check = model_check(progress=hashed)
                if not job.check.ok:
                    job.end("failed", f"The audit did not start. {job.check.summary}")
                    return
            comps = components_for(conn, ai_review)
            comps.label_settled = label_all
            job.components = comps

            def progress(done: int, total: int, d: object) -> None:
                job.done = done
                if job.stop.is_set() and done < total:
                    raise pipeline.RunStopped(f"stopped by {actor} after {done} of {total} claims")

            with keep_awake() as how:
                job.awake = how
                job.message = "Labeling."
                result = pipeline.run_audit(
                    conn,
                    comps,
                    claim_ids=list(order),
                    progress=progress,
                    config={"started_from": "review screen", "started_by": actor},
                )
            record_speed(comps)
            tally: dict[str, int] = {}
            for d in result.decisions:
                tally[d.verdict.value] = tally.get(d.verdict.value, 0) + 1
            words = ", ".join(f"{n} {v}" for v, n in sorted(tally.items()))
            job.end(
                "done",
                f"The audit finished all {len(result.decisions)} claims ({words}). Review them in "
                "the claims queue; no claim is supported until you accept its key evidence.",
            )
        except pipeline.RunStopped:
            job.end(
                "stopped",
                f"Stopped after {job.done} of {job.total} claims. Finished claims keep their "
                "work; resume to label the rest.",
            )
        except CloudPaused as e:
            job.end(
                "stopped",
                f"Paused after {job.done} of {job.total} claims: {e}. No claim was labeled by "
                "another model. Resume to try the cloud model again, or turn cloud AI off for "
                "this case in Setup and run the audit again to label the whole case locally.",
            )
        except (pipeline.ComponentsMissing, ModelConfigError) as e:
            support_errors.note("audit", e)
            job.end("failed", f"The audit did not start: {e}.")
        except (InvariantViolation, ModelUnavailable) as e:
            support_errors.note("audit", e)
            job.end(
                "failed",
                f"The audit stopped after {job.done} of {job.total} claims: {e}. Finished claims "
                "keep their work; resume to label the rest.",
            )
        finally:
            conn.close()
            if cloud_opt_in:  # the cloud labeler holds the API key; locking must not leave it
                job.components = None

    return run


def propose_job(*, extractor_for: ExtractorFor) -> Callable[[Job], None]:
    """The local model proposes claims, one paragraph per transaction, so a stop keeps what is
    done and starting again skips paragraphs that already have claims."""

    def run(job: Job) -> None:
        from core.audit._llm_json import PromptMissingError
        from core.claims.propose import load_paragraphs, propose_claims

        conn = _open(job.db)
        try:
            todo = [
                p
                for p in load_paragraphs(conn)
                if conn.execute(
                    "SELECT 1 FROM claims WHERE paragraph_id = ? LIMIT 1", (p.id,)
                ).fetchone()
                is None
            ]
            job.total = len(todo)
            if not todo:
                job.end("done", "Every paragraph already has claims; nothing to propose.")
                return
            try:
                extractor = extractor_for(conn)
            except (ValueError, ModelConfigError, PromptMissingError) as e:
                support_errors.note("propose", e)
                job.end("failed", f"Claim proposal did not start: {e}.")
                return
            proposed = dropped = 0
            with keep_awake() as how:
                job.awake = how
                for p in todo:
                    if job.stop.is_set():
                        job.end(
                            "stopped",
                            f"Stopped after {job.done} of {job.total} paragraphs; {proposed} "
                            "claims proposed. Propose again to continue.",
                        )
                        return
                    r = propose_claims(conn, extractor, [p])  # type: ignore[arg-type]
                    proposed += len(r.claims)
                    dropped += len(r.drops)
                    job.done += 1
            job.end(
                "done",
                f"{proposed} claims proposed from {job.total} paragraphs"
                + (
                    f"; {dropped} proposals dropped by the claim checks (the audit log says why)"
                    if dropped
                    else ""
                )
                + ". Accept, edit or remove each one.",
            )
        except ModelUnavailable as e:
            support_errors.note("propose", e)
            job.end("failed", f"Claim proposal stopped after {job.done} paragraphs: {e}.")
        finally:
            conn.close()

    return run


def model_check_job(model_check: ModelCheckFn) -> Callable[[Job], None]:
    def run(job: Job) -> None:
        def hashed(done: int, total: int) -> None:
            job.hashed = (done, total)

        job.check = model_check(progress=hashed)
        job.end("done" if job.check.ok else "failed", job.check.summary)

    return run
