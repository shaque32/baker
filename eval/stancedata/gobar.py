"""The go or no-go rule for adopting Baker's own stance model, fixed before any training.

GO_BAR.md explains it in words; this module is the same rule as code, so the decision is a
function of measured numbers and nobody's judgment after the fact. Changing a number here after
a candidate's test result is known is not allowed (GO_BAR.md, "Rules").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The bar to beat: Qwen3-14B Q4_K_M with the signed stance prompt, 22.61 s per stance call on
# Arsh's 24 GB Mac (thread "Model speed and claim proposal", run posted 2026-10-08 21:06 UTC).
BASELINE_MODEL = "qwen3-14b-q4_k_m"
BASELINE_SECONDS_PER_CALL = 22.61
MIN_SPEEDUP = 5.0
MAX_SECONDS_PER_CALL = BASELINE_SECONDS_PER_CALL / MIN_SPEEDUP  # 4.52 s

# The four "Expert confirms" bars (eval/probe/README.md), applied to both test sets, and, since
# guide v0.3 (Arsh, 2026-10-14), zero items of the trap families it moved to complicates shown as
# supports (eval.probe.run_probe.MOVED_TRAPS).
BARS: dict[str, float] = {
    "stance_valid_output": 1.0,  # at least
    "supports_recall": 0.90,  # at least
    "contradicts_precision": 0.90,  # at least
    "contradicts_shown_as_supports": 0,  # at most
    "moved_traps_shown_as_supports": 0,  # at most (guide v0.3)
}
AT_MOST = {"contradicts_shown_as_supports", "moved_traps_shown_as_supports"}

# A test set counts only with enough gated items for its zero-error bar to mean something.
MIN_GATED = {"probe": 78, "heldout": 1000}
MIN_GOLD_CONTRADICTS = {"probe": 8, "heldout": 420}

# Condition 5: Baker's real pipeline on the hidden case02, aggregate numbers only.
CASE02_AT_MOST = {"false_supported": 0, "false_contradicted": 0}
CASE02_MIN_VERDICT_ACCURACY = 0.80


@dataclass
class Decision:
    go: bool
    reasons: list[str] = field(default_factory=list)  # every failed condition, in plain words


def _check_set(name: str, result: dict[str, Any] | None, reasons: list[str]) -> None:
    if result is None:
        reasons.append(f"{name}: no result")
        return
    gated = result.get("gated") or {}
    n = gated.get("n", 0)
    if n < MIN_GATED[name]:
        reasons.append(f"{name}: {n} gated items, fewer than {MIN_GATED[name]} (sample unsigned?)")
        return
    if gated.get("gold_contradicts", 0) < MIN_GOLD_CONTRADICTS[name]:
        reasons.append(f"{name}: fewer than {MIN_GOLD_CONTRADICTS[name]} gold contradicts")
    for bar, value in BARS.items():
        got = gated.get(bar)
        ok = got is not None and (got <= value if bar in AT_MOST else got >= value)
        if not ok:
            sign = "<=" if bar in AT_MOST else ">="
            reasons.append(f"{name}: {bar} is {got}, needs {sign} {value}")


def decide(
    *,
    probe: dict[str, Any] | None,
    heldout: dict[str, Any] | None,
    case02: dict[str, Any] | None,
    seconds_per_call: float | None,
    contamination_passed: bool,
) -> Decision:
    """probe and heldout are eval.stancedata.score.score() results for the same model file;
    case02 holds that model's aggregate numbers from Baker's pipeline on case02 (GO_BAR.md,
    condition 5): false_supported, false_contradicted and verdict_accuracy."""
    reasons: list[str] = []
    if not contamination_passed:
        reasons.append("overlap check did not pass on the training file used")
    _check_set("probe", probe, reasons)
    _check_set("heldout", heldout, reasons)
    if case02 is None:
        reasons.append("case02: no result")
    else:
        for key, most in CASE02_AT_MOST.items():
            if case02.get(key) is None or case02[key] > most:
                reasons.append(f"case02: {key} is {case02.get(key)}, needs <= {most}")
        acc = case02.get("verdict_accuracy")
        if acc is None or acc < CASE02_MIN_VERDICT_ACCURACY:
            reasons.append(
                f"case02: verdict accuracy is {acc}, needs >= {CASE02_MIN_VERDICT_ACCURACY:.2f}"
            )
    if seconds_per_call is None:
        reasons.append("speed not measured")
    elif seconds_per_call > MAX_SECONDS_PER_CALL:
        reasons.append(
            f"speed: {seconds_per_call:.2f} s per stance call, needs <= {MAX_SECONDS_PER_CALL:.2f}"
        )
    return Decision(go=not reasons, reasons=reasons)
