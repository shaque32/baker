#!/usr/bin/env bash
# Mac run for stance prompt v1.2 and the 14B-vs-Opus test (2026-10-16).
# Run from the repo root with the venv active:  bash eval/probe/mac_v12.sh
# Needs eval/probe/models.local.json with the 14B (the file the earlier Mac runs used).
# Everything is synthetic and offline. Paste back the file it prints at the end.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
OUT="${OUT:-eval/out/mac_v12}"
mkdir -p "$OUT"
{
  echo "commit $(git rev-parse --short HEAD)"
  python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())"
  echo "$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
} > "$OUT/versions.txt"

echo "1/2 the 14B on the signed probe set with stance prompt v1.2 (stance only, 2 answers per item)"
python -m eval.probe.run_probe --models "$MODELS" --probe-set eval/gold/probe/probe.jsonl \
  --stance-only --repeat 2 --layout product_members --out "$OUT/probe"

echo "2/2 the 14B half of the 14B-vs-Opus test (claims, case01 audit without the sheet)"
python -m eval.bench.fair_steps --arm local --models "$MODELS" --out "$OUT/fair"

{
  echo "# Mac results, stance v1.2 and the 14B-vs-Opus test ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo
  cat "$OUT/versions.txt"
  echo
  cat "$OUT/probe/summary.md"
  echo
  cat "$OUT/fair/summary.md"
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
