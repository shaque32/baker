#!/usr/bin/env bash
# Wave 3 model test on a Mac: which model the alpha ships with, and how long a case takes.
# Run from the repo root with the venv active:  bash eval/probe/mac_wave3.sh
# Needs eval/probe/models.local.json listing the GGUF files to compare (8B and 14B).
# Everything is synthetic and offline. Paste back the file it prints at the end.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
# The signed probe set (P001-P088) lives in eval/gold/probe/; older checkouts have the drafts file.
if [ -f eval/gold/probe/probe.jsonl ]; then DEFAULT_PROBE=eval/gold/probe/probe.jsonl
else DEFAULT_PROBE=eval/probe_draft/probe_draft.jsonl; fi
PROBE_SET="${PROBE_SET:-$DEFAULT_PROBE}"
OUT="${OUT:-eval/out/wave3_mac}"
RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))

if [ "$RAM_GB" -gt 16 ]; then
  NCTX="${NCTX:-8192}"
  CLAIMS="${CLAIMS:-}"                 # whole case
else
  NCTX="${NCTX:-4096}"                 # a 14B model only fits with a small context
  CLAIMS="${CLAIMS:-C02,C05,C12}"      # three claims (69 stance calls), projected to the case
fi
CLAIM_ARGS=()
if [ -n "$CLAIMS" ]; then CLAIM_ARGS=(--claims "$CLAIMS"); fi

mkdir -p "$OUT"
python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())" \
  > "$OUT/versions.txt"
ls -l $(python -c "import json; print(' '.join(m['path'] for m in json.load(open('$MODELS'))))") \
  >> "$OUT/versions.txt" 2>&1 || true
echo "1/3 stance probe on the signed set (stance only; the reviewer decides nothing now)"
python -m eval.probe.run_probe --models "$MODELS" \
  --probe-set "$PROBE_SET" --stance-only --repeat 1 \
  --n-ctx "$NCTX" --out "$OUT/probe"

echo "2/3 timed audit of case01, then the rerun an expert triggers"
python -m eval.probe.time_case --models "$MODELS" --n-ctx "$NCTX" ${CLAIM_ARGS[@]+"${CLAIM_ARGS[@]}"} \
  --out "$OUT/speed"

echo "3/3 claim proposal recall against case01 gold"
python -m eval.probe.claim_recall --models "$MODELS" --n-ctx "$NCTX" --out "$OUT/claims"

{
  echo "# Wave 3 Mac results ($(date -u +%Y-%m-%dT%H:%MZ), ${RAM_GB} GB, n_ctx ${NCTX})"
  echo
  cat "$OUT/versions.txt"
  echo
  cat "$OUT/probe/summary.md"
  echo
  cat "$OUT/speed/summary.md"
  echo
  cat "$OUT/claims/summary.md"
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
