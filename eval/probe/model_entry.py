"""Which entry of a probe models file (models.local.json) a local run uses.

Lives in eval/probe/ because the Windows installer ships this folder (the speed and repeat
checks run from an installed copy) but not eval/bench/.
"""

from __future__ import annotations

from typing import Any


def pick_entry(entries: list[dict[str, Any]], name: str | None) -> dict[str, Any]:
    """The models-file entry the local arm uses: the one named, else the only one, else the one
    whose name says 14B. eval/probe/mac_v12.sh probes the same entry."""
    if name:
        pick = [e for e in entries if e["name"] == name]
    elif len(entries) == 1:
        pick = entries
    else:
        pick = [e for e in entries if "14b" in e["name"].lower()]
    if len(pick) != 1:
        names = ", ".join(e["name"] for e in entries)
        raise SystemExit(f"name one model with --model-name or MODEL_NAME (have: {names})")
    return pick[0]
