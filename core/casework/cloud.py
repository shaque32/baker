"""Whether a case's stance labels may come from the cloud model, decided per case.

Local by default; cloud only by opt-in. A case uses the cloud stance labeler (core/llm/cloud.py)
only when all of these hold, and otherwise the local model labels it, exactly as before:
1. The expert attested, for this case, that its protective order allows cloud AI.
2. The expert did not mark the case as possibly containing CSAM. Such material stays in the
   government's control (18 U.S.C. 3509(m)), so a marked case never uses cloud, whatever (1) says.
3. An Anthropic key is set up on this computer (the expert's own; Mabillon runs no server).
4. The configured model, at its configured effort, passed Mabillon's signed stance test with the
   cloud stance prompt it would read (core/audit/prompts/stance_cloud.md; core/llm/cloud.py,
   PROBE_PASSED). Opus 5.5 at medium effort is listed (signed by Arsh 2026-10-20).

Then every stance label in the case comes from the cloud model; labels never mix models. If
the cloud model stops answering, the audit pauses (core/audit/_local_model.py, CloudPort) and
the expert resumes to retry it, or turns cloud AI off here and runs the case again locally.
Every request is logged in the case's audit log before it is sent (SentLog).

The choice lives only in the case's hash-chained audit log (inside the case database, so an
encrypted case keeps it encrypted): the latest set_cloud entry by an expert, with who made it,
when, and the words they agreed to. Nothing about it is written to the readable case.json.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core import db
from core.llm import cloud as cloud_llm
from core.review.actions import _expert

ACTION = "set_cloud"
ATTESTATION = (
    "This case's protective order (or the court or the government's consent) allows its "
    "evidence to be sent to a cloud AI service under my firm's account, and my client has "
    "given informed consent to it."
)
CSAM_NOTE = "This case may contain child sexual abuse material."


@dataclass(frozen=True)
class CloudChoice:
    use: bool
    why: str  # one plain sentence for the screen, the run's config and the report
    config: cloud_llm.CloudConfig | None = None

    def record(self) -> dict[str, Any]:
        out: dict[str, Any] = {"use": self.use, "why": self.why}
        if self.config is not None:
            out["model"] = self.config.model
            out["effort"] = self.config.effort
        return out


def case_cloud(conn: sqlite3.Connection) -> dict[str, Any]:
    """The case's current cloud choice: the latest set_cloud entry an expert made in its audit
    log, or {} if there is none. Cloud counts as allowed only when that entry carries the
    attestation text word for word; anything else reads as not allowed."""
    try:
        row = conn.execute(
            "SELECT at_utc, actor, payload_json FROM audit_log WHERE action = ?"
            " AND actor LIKE 'expert:%' ORDER BY seq DESC LIMIT 1",
            (ACTION,),
        ).fetchone()
    except db.OperationalError:
        return {}
    if row is None:
        return {}
    try:
        payload = json.loads(row[2])
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    csam = payload.get("csam") is True
    allowed = payload.get("allowed") is True and not csam
    allowed = allowed and payload.get("attestation") == ATTESTATION
    out: dict[str, Any] = {"allowed": allowed, "csam": csam}
    if allowed:
        out["attested_by"] = row[1]
        out["attested_at"] = row[0]
    return out


def choose(
    conn: sqlite3.Connection,
    load: Callable[[], cloud_llm.CloudConfig] = cloud_llm.load_config,
) -> CloudChoice:
    """The cloud decision for one case, from its audit log and the expert's key."""
    c = case_cloud(conn)
    if c.get("csam") is True:
        return CloudChoice(False, "Local model: the case is marked as possibly containing CSAM, "
                                  "so it never uses cloud AI.")  # fmt: skip
    if c.get("allowed") is not True:
        return CloudChoice(False, "Local model: nobody has attested that this case's protective "
                                  "order allows cloud AI.")  # fmt: skip
    try:
        cfg = load()
    except cloud_llm.CloudConfigError as e:
        return CloudChoice(False, f"Local model: cloud AI is allowed for this case, but {e}.")
    version = _stance_prompt_version()
    if (cfg.model, cfg.effort, version) not in cloud_llm.PROBE_PASSED:
        return CloudChoice(
            False,
            f"Local model: cloud AI is allowed for this case, but {cfg.model} ({cfg.effort} "
            "effort) has not passed "
            "Mabillon's signed stance test with the cloud stance prompt, so the local model "
            "labels it.",
        )
    who = str(c["attested_by"]).removeprefix("expert:")
    when = str(c["attested_at"])[:10]
    return CloudChoice(
        True,
        f"Cloud model {cfg.model} ({cfg.effort} effort), attested by {who} on {when}; if it "
        "stops answering, the audit pauses rather than mix in local labels.",
        cfg,
    )


def _stance_prompt_version() -> str | None:
    from core.audit._llm_json import PromptMissingError, load_prompt, prompt_version
    from core.audit.stance import CLOUD_PROMPT_FILE

    try:
        return prompt_version(load_prompt(CLOUD_PROMPT_FILE))
    except PromptMissingError:
        return None


def set_cloud(
    conn: sqlite3.Connection,
    actor: str,
    *,
    allowed: bool,
    csam: bool,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Record the expert's cloud choice for a case in its audit log (inside the case database,
    so an encrypted case keeps it encrypted; nothing goes in the readable case.json)."""
    from core.casework.cases import _logged

    _expert(actor)
    payload: dict[str, Any] = {"allowed": bool(allowed) and not csam, "csam": bool(csam)}
    if payload["allowed"]:
        payload["attestation"] = ATTESTATION
    if csam:
        payload["csam_note"] = CSAM_NOTE
    _logged(conn, clock(), actor, ACTION, payload)
    return case_cloud(conn)
