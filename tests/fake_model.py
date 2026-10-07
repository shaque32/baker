"""A scripted stand-in for the local model. No weights, no network."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

Reply = str | dict[str, Any] | Exception | Callable[[str], str]


class FakeModel:
    def __init__(self, *replies: Reply, run_id: str | None = "run:fake:1") -> None:
        self._replies = list(replies)
        self._run_id = run_id
        self.prompts: list[str] = []
        self.schemas: list[Mapping[str, Any]] = []

    @property
    def run_id(self) -> str:
        return self._run_id  # type: ignore[return-value]

    def generate(self, prompt: str, json_schema: Mapping[str, Any]) -> str:
        self.prompts.append(prompt)
        self.schemas.append(json_schema)
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply(prompt)
        if isinstance(reply, dict):
            return json.dumps(reply)
        return reply


def make_assumption(text: str, claim_id: str = "c1"):
    """A v0.2 assumption for model-pass tests. Params are irrelevant to the passes."""
    from core.contracts import (
        Assumption,
        AssumptionKind,
        AssumptionParams,
        ProvenanceTier,
        assumption_id,
    )

    params = AssumptionParams(quoted_text=text)
    return Assumption(
        id=assumption_id(claim_id, "test_meaning", params),
        claim_id=claim_id,
        kind=AssumptionKind.MEANING,
        template_id="test_meaning",
        template_version="0",
        params=params,
        text=text,
        is_core=True,
        tier=ProvenanceTier.INFERRED,
    )
