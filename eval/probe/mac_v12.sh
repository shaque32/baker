#!/usr/bin/env bash
# Mac run for stance prompt v1.2 and the 14B-vs-Opus test (2026-10-16).
# Run from the repo root with the venv active:  bash eval/probe/mac_v12.sh
# Needs eval/probe/models.local.json with the 14B (the file the earlier Mac runs used).
# Everything is synthetic and offline. Paste back the file it prints at the end.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
# A fresh folder per run: the probe appends to its call log, so a reused folder would mix runs.
OUT="${OUT:-eval/out/mac_v12/$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$OUT" ]; then echo "$OUT already exists; set OUT to a new folder" >&2; exit 1; fi
mkdir -p "$OUT"
# Both steps use the same one model: the 14B, or the entry MODEL_NAME names.
python -c 'import json, sys; from eval.bench.fair_steps import pick_entry
json.dump([pick_entry(json.load(open(sys.argv[1])), sys.argv[2] or None)], open(sys.argv[3], "w"), indent=2)' \
  "$MODELS" "${MODEL_NAME:-}" "$OUT/model.json"
{
  echo "commit $(git rev-parse --short HEAD)"
  python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())"
  echo "$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
} > "$OUT/versions.txt"

echo "1/3 the 14B on the signed probe set with stance prompt v1.2 (stance only, 2 answers per item)"
python -m eval.probe.run_probe --models "$OUT/model.json" --probe-set eval/gold/probe/probe.jsonl \
  --stance-only --repeat 2 --layout product_members --out "$OUT/probe"

# The 14B has never run v1.1 on this set, and #93 merges only if v1.2 holds supports recall and
# contradicts precision at v1.1's level with 0 moved traps shown as supports. Same set, layout and
# machine; the first answer decides in both runs, so one answer per item is enough here.
echo "2/3 the same probe with stance prompt v1.1 (the body on main today), the baseline"
python -m eval.probe.run_probe --models "$OUT/model.json" --probe-set eval/gold/probe/probe.jsonl \
  --stance-only --repeat 1 --layout product_members --stance-prompt eval/probe/stance_v1_1_signed.md \
  --out "$OUT/probe_v1_1"

echo "3/3 the 14B half of the 14B-vs-Opus test (claims, case01 audit without the sheet)"
python -m eval.bench.fair_steps --arm local --models "$OUT/model.json" --out "$OUT/fair"

{
  echo "# Mac results, stance v1.2 and the 14B-vs-Opus test ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo
  cat "$OUT/versions.txt"
  echo
  echo "## Stance prompt v1.2"
  cat "$OUT/probe/summary.md"
  echo
  echo "## Stance prompt v1.1 (baseline)"
  cat "$OUT/probe_v1_1/summary.md"
  echo
  cat "$OUT/fair/summary.md"
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
