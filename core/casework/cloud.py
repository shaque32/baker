"""Whether a case's stance labels may come from the cloud model, decided per case.

Cloud first, never cloud only. A case uses the cloud stance labeler (core/llm/cloud.py) only
when all of these hold, and otherwise the local model labels it, exactly as before:
1. The expert attested, for this case, that its protective order allows cloud AI.
2. The expert did not mark the case as possibly containing CSAM. Such material stays in the
   government's control (18 U.S.C. 3509(m)), so a marked case never uses cloud, whatever (1) says.
3. An Anthropic key is set up on this computer (the expert's own; Baker runs no server).

Even then, any failed cloud call falls back to the local model (core/audit/_local_model.py,
FallbackPort), and every evidence item records which model labelled it.

The choice lives in the case's settings file (case.json) under "cloud", and every change is an
entry in the case's hash-chained audit log, with who made it and the words they agreed to.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from core.llm import cloud as cloud_llm
from core.review.actions import _expert

SETTINGS_KEY = "cloud"
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


def case_cloud(settings: Mapping[str, Any]) -> dict[str, Any]:
    raw = settings.get(SETTINGS_KEY)
    return raw if isinstance(raw, dict) else {}


def choose(
    settings: Mapping[str, Any],
    load: Callable[[], cloud_llm.CloudConfig] = cloud_llm.load_config,
) -> CloudChoice:
    """The cloud decision for one case, from its settings and the expert's key."""
    c = case_cloud(settings)
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
    who = str(c.get("attested_by", "?")).removeprefix("expert:")
    when = str(c.get("attested_at", "?"))[:10]
    return CloudChoice(
        True,
        f"Cloud model {cfg.model} ({cfg.effort} effort), attested by {who} on {when}; the "
        "local model answers any call the cloud cannot.",
        cfg,
    )


def set_cloud(
    case: Any,
    conn: sqlite3.Connection,
    actor: str,
    *,
    allowed: bool,
    csam: bool,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Record the expert's cloud choice for a case: in its settings and in its audit log.
    `case` is a core.casework.cases.Case (anything with settings and save_settings)."""
    from core.casework.cases import _logged

    _expert(actor)
    at = clock()
    entry: dict[str, Any] = {"allowed": bool(allowed) and not csam, "csam": bool(csam)}
    if entry["allowed"]:
        entry["attested_by"] = actor
        entry["attested_at"] = at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        entry["attestation"] = ATTESTATION
    payload = {k: v for k, v in entry.items() if k != "attested_at"}
    if csam:
        payload["csam_note"] = CSAM_NOTE
    _logged(conn, at, actor, "set_cloud", payload)
    case.save_settings(**{SETTINGS_KEY: entry})
    return entry
