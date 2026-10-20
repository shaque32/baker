"""Screen newer local models against the 14B on the signed probe set (stance only).

EVAL ONLY. Arsh asked whether Qwen3-14B is the best local model (thread "Better local stance
model", 2026-10-20) and said "go" to this screen. The candidates, the settings and the pass rule
below were written down before any run (write-up:
/mnt/project-files/baker/local-model/2026-10-20-better-local-model.md).

Each candidate runs the signed probe set (eval/gold/probe/probe.jsonl), stance only, layout
product_members, runtime flash, n_ctx 8192, thinking off, one answer per item, with both signed
stance prompts: v1.1 (eval/probe/stance_v1_1_signed.md, the 14B's) and v1.2
(core/audit/prompts/stance_cloud.md, the one Opus passed with). Prompts and gold are unchanged.

Stage 1 pass, on either prompt (signed, undisputed items): all four Expert-confirms bars
(supports recall >= 90%, contradicts precision >= 90%, 0 contradicts shown as supports, 100%
valid output) and 0 moved traps shown as supports. Picking the better of two prompts is a small
advantage, so a pass only earns stage 2 (a repeat run with identical output, then case01 with
>= 80% accuracy and 0 false supported), which this file does not run. Among models that pass
stage 2 the fastest wins. Both the probe and case01 help pick, so before any swap the pick is
confirmed on fresh held-out items it was not chosen on. Switching the product's local model is a
separate PR and Arsh's call.

Usage (from the repo root; eval/probe/mac_candidates.sh runs all of it):
  python -m eval.probe.candidates download --dir ~/baker-models [NAME ...]
  python -m eval.probe.candidates models-file NAME --dir ~/baker-models --out model.json
  python -m eval.probe.candidates chat-template NAME
  python -m eval.probe.candidates verdict OUT
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.llm.runtime import sha256_file


@dataclass(frozen=True)
class Candidate:
    name: str
    repo: str  # Hugging Face repo the GGUF file comes from
    revision: str  # the repo commit, so the same bytes download every time
    file: str
    sha256: str  # from the repo's LFS pointer, 2026-10-20
    license: str  # SPDX id from the model card, checked 2026-10-20
    chat_template: str  # "gguf" or "no-think" (core/llm/runtime.py)
    gigabytes: float


# Fastest first, so the first results arrive early (speeds are estimates until measured).
CANDIDATES = (
    Candidate(
        name="gemma-4-26b-a4b-qat-q4_0",
        repo="google/gemma-4-26B-A4B-it-qat-q4_0-gguf",
        revision="d1c082be9cf3c8a514acf63b8761f4b41935842e",
        file="gemma-4-26B_q4_0-it.gguf",
        sha256="3eca3b8f6d7baf218a7dd6bba5fb59a56ee25fe2d567b6f5f589b4f697eca51d",
        license="Apache-2.0",
        chat_template="gguf",  # its template already starts the answer with an empty thought
        gigabytes=14.4,
    ),
    Candidate(
        name="gemma-4-12b-qat-q4_0",
        repo="google/gemma-4-12B-it-qat-q4_0-gguf",
        revision="29d097773436b69ff9feafd636ab4cf873786537",
        file="gemma-4-12b-it-qat-q4_0.gguf",
        sha256="93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b",
        license="Apache-2.0",
        chat_template="gguf",
        gigabytes=7.0,
    ),
    Candidate(
        name="qwen3.8-27b-ud-iq4_xs",
        repo="unsloth/Qwen3.8-27B-GGUF",
        revision="4ca720788d1e01f1bff70c033e0d0028fd02e502",
        file="Qwen3.8-27B-UD-IQ4_XS.gguf",
        sha256="40fac4050e940397dbf13087afd50f4734a11805bf9d65ef8ddd7483470e6199",
        license="Apache-2.0",
        chat_template="no-think",  # its template opens a thinking block by default
        gigabytes=14.3,
    ),
)
BY_NAME = {c.name: c for c in CANDIDATES}
PROMPTS = {
    "v1.1": "eval/probe/stance_v1_1_signed.md",
    "v1.2": "core/audit/prompts/stance_cloud.md",
}


def candidate(name: str) -> Candidate:
    if name not in BY_NAME:
        raise SystemExit(f"unknown candidate {name!r}; one of {', '.join(BY_NAME)}")
    return BY_NAME[name]


def models_entry(c: Candidate, models_dir: Path) -> dict[str, Any]:
    """The run_probe models-file entry: LlamaCppModel checks the sha256 before loading."""
    return {
        "name": c.name,
        "path": str(models_dir / c.file),
        "sha256": c.sha256,
        "license": c.license,
        "source": f"https://huggingface.co/{c.repo}/blob/{c.revision}/{c.file}",
    }


def download(names: list[str], models_dir: Path) -> int:
    """Fetch each file at its pinned revision unless it is already there, then check its hash."""
    from huggingface_hub import hf_hub_download  # eval only; mac_candidates.sh installs it

    models_dir.mkdir(parents=True, exist_ok=True)
    bad = 0
    for c in (candidate(n) for n in names):
        path = models_dir / c.file
        if not path.is_file():
            print(f"downloading {c.repo}/{c.file} ({c.gigabytes} GB)", file=sys.stderr)
            hf_hub_download(c.repo, c.file, revision=c.revision, local_dir=models_dir)
        digest = sha256_file(path)
        ok = digest == c.sha256
        bad += not ok
        print(f"{c.name}: sha256 {'ok' if ok else 'MISMATCH ' + digest}", file=sys.stderr)
    return 1 if bad else 0


def stage1(row: dict[str, Any]) -> tuple[bool, list[str]]:
    """Whether one run_probe result passes stage 1, and the bars it misses."""
    if row.get("load_error"):
        return False, [f"did not load: {row['load_error']}"]
    ec = row.get("expert_confirms") or {}
    missed = [name for name, met in (ec.get("bars") or {}).items() if not met]
    if not ec.get("bars"):
        missed.append("no Expert-confirms result")
    if ec.get("moved_traps_shown_as_supports") != 0:
        missed.append(f"moved traps shown as supports: {ec.get('moved_traps_shown_as_supports')}")
    return not missed, missed


def _pct(v: object) -> str:
    return "n/a" if v is None else f"{v:.0%}" if isinstance(v, float) else str(v)


def _with_ci(rate: object, n: object, ci: object) -> str:
    """ "95% of 40 [83-99%]": the rate, its denominator and its Wilson 95% interval."""
    if rate is None:
        return f"n/a of {n}"
    text = f"{_pct(rate)} of {n}"
    if isinstance(ci, list | tuple) and len(ci) == 2:
        text += f" [{ci[0]:.0%}-{ci[1]:.0%}]"
    return text


def _predicted_contradicts(ec: dict[str, Any]) -> int:
    return sum(row.get("contradicts", 0) for row in (ec.get("confusion") or {}).values())


def _misses(row: dict[str, Any]) -> str:
    """The gated items the model got wrong, as id (expected -> got), for bucketing by hand."""
    out = []
    for f in row.get("stance_failures") or []:
        if "expected" in f:
            out.append(f"{f['id']} ({f['expected']} -> {f['got']})")
        else:
            out.append(f"{f['id']} (no valid answer: {f.get('error')})")
    return ", ".join(out) or "none"


def verdict(out: Path) -> str:
    """RESULTS.md for a finished screen: one row per model and prompt, stage 1, the items each
    run got wrong, and what each run ran on."""
    lines = [
        "Supports recall and contradicts precision on signed, undisputed items: rate, of n,"
        " [Wilson 95% interval].",
        "",
        "| model | prompt | supports recall | contradicts precision | contradicts as supports"
        " | moved traps as supports | valid output | s/call | tokens/s | stage 1 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    passed: dict[str, list[str]] = {}
    unfinished: list[str] = []
    misses: list[str] = []
    runs: list[str] = []
    for c in CANDIDATES:
        for version in PROMPTS:
            summary = out / c.name / version / "summary.json"
            if not summary.is_file():
                lines.append(f"| {c.name} | {version} | not run | | | | | | | |")
                unfinished.append(f"{c.name} {version}")
                continue
            for row in json.loads(summary.read_text(encoding="utf-8")):
                ok, missed = stage1(row)
                ec = row.get("expert_confirms") or {}
                rep = ec.get("reported") or {}
                cells = [
                    _with_ci(
                        ec.get("supports_recall"),
                        rep.get("gold_supports"),
                        rep.get("supports_recall_95ci"),
                    ),
                    _with_ci(
                        ec.get("contradicts_precision"),
                        _predicted_contradicts(ec),
                        rep.get("contradicts_precision_95ci"),
                    ),
                    _pct(ec.get("contradicts_shown_as_supports")),
                    _pct(ec.get("moved_traps_shown_as_supports")),
                    _pct(ec.get("stance_valid_output")),
                    str(row.get("mean_seconds_per_stance_call") or "n/a"),
                    str(row.get("tokens_per_second") or "n/a"),
                    "pass" if ok else "misses: " + "; ".join(missed),
                ]
                lines.append(f"| {c.name} | {version} | " + " | ".join(cells) + " |")
                if ok:
                    passed.setdefault(c.name, []).append(version)
                if row.get("load_error"):
                    unfinished.append(f"{c.name} {version}")
                else:
                    misses.append(f"- {c.name} {version}: {_misses(row)}")
                    params = row.get("params") or {}
                    runs.append(
                        f"- {c.name} {version}: sha256 {row.get('sha256')}, seed"
                        f" {params.get('seed')}, temperature {params.get('temperature')},"
                        f" n_ctx {params.get('n_ctx')}, chat template"
                        f" {params.get('chat_template', 'gguf')}, prompt"
                        f" {row.get('stance_prompt')}, GPU memory used"
                        f" {row.get('vram_used_mib', 'n/a')} MiB"
                    )
    lines.append("")
    if passed:
        for name, versions in passed.items():
            lines.append(
                f"Stage 1 PASS: {name} with {', '.join(versions)}. It goes to stage 2 (repeat"
                " run, then case01). The probe and case01 both helped pick it, so a swap also"
                " needs fresh held-out items it was not picked on."
            )
    elif unfinished:
        lines.append(
            f"Stage 1 INCOMPLETE: {', '.join(unfinished)} did not run or load, and nothing that"
            " ran passes. No decision until those runs finish."
        )
    else:
        lines.append("Stage 1: no candidate passes. The 14B stays the local model.")
    lines += ["", "## Items each run got wrong (gated)", "", *misses]
    lines += ["", "## What each run ran on", "", *runs]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download")
    d.add_argument("names", nargs="*", default=[c.name for c in CANDIDATES])
    d.add_argument("--dir", type=Path, required=True)
    m = sub.add_parser("models-file")
    m.add_argument("name")
    m.add_argument("--dir", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True)
    t = sub.add_parser("chat-template")
    t.add_argument("name")
    v = sub.add_parser("verdict")
    v.add_argument("out", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "download":
        return download(args.names, args.dir.expanduser())
    if args.cmd == "models-file":
        entry = models_entry(candidate(args.name), args.dir.expanduser())
        args.out.write_text(json.dumps([entry], indent=2) + "\n", encoding="utf-8")
        return 0
    if args.cmd == "chat-template":
        print(candidate(args.name).chat_template)
        return 0
    text = verdict(args.out)
    (args.out / "VERDICT.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
