"""Cloud upper bound for the probe set. EVAL ONLY: core/ never imports this.

Runs the same probe items and prompts through Claude to show the ceiling a local model is
compared with. Agreeing with Claude is not the same as being right; only the probe labels score.
Never run this on real case data. Only the synthetic probe files go to the API.

Usage: python -m eval.bench.claude_bench [--model claude-opus-5-5] [--out eval/out/bench]
Needs `pip install .[bench]` and Anthropic credentials (ANTHROPIC_API_KEY or `ant auth login`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from core.llm.runtime import GenerationParams, ModelOutput, parse_json_output
from eval.probe.run_probe import HERE, load_items, run_model, table

DEFAULT_MODEL = "claude-opus-5-5"


class ClaudeModel:
    """Same `generate_json` surface as the local runtime, backed by the Claude API.

    No refusal fallbacks: a silent switch to another model would corrupt the benchmark, so a
    refusal is scored as an invalid output instead.
    """

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "medium") -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self.name = model
        self.sha256 = f"api:{model}"
        self.effort = effort

    def generate_json(
        self, prompt: str, schema: dict[str, Any], params: GenerationParams | None = None
    ) -> ModelOutput:
        start = time.perf_counter()
        resp = self._client.messages.create(
            model=self.name,
            max_tokens=4000,
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.perf_counter() - start
        if resp.stop_reason == "refusal":
            return ModelOutput("", None, "refusal", seconds=elapsed)
        text = "".join(b.text for b in resp.content if b.type == "text")
        parsed, error = parse_json_output(text, schema)
        return ModelOutput(
            raw_text=text,
            parsed=parsed,
            error=error,
            prompt_tokens=resp.usage.input_tokens,
            completion_tokens=resp.usage.output_tokens,
            seconds=elapsed,
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--reviewer", type=Path, default=HERE / "smoke_reviewer.jsonl")
    ap.add_argument("--stance", type=Path, default=HERE / "smoke_stance.jsonl")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--out", type=Path, default=Path("eval/out/bench"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    model = ClaudeModel(args.model, args.effort)
    res = run_model(model, load_items(args.reviewer), load_items(args.stance),
                    GenerationParams(), args.repeat, args.out)  # fmt: skip
    (args.out / "summary.json").write_text(json.dumps([res], indent=2, ensure_ascii=False))
    print(table([res]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
