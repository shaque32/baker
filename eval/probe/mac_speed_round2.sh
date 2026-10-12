#!/usr/bin/env bash
# Faster calls, round 2, on a Mac: the runtime speed settings and stance prompt v1.1 in one
# sitting (eval/probe/speed_round2.py says what runs and the rules that decide).
#
#   cd baker && source .venv/bin/activate
#   bash eval/probe/mac_speed_round2.sh
#
# Needs eval/probe/models.local.json (the file the earlier Mac runs used). With several models
# listed it runs the 14B; MODEL=<name> picks another. Run nothing else on the Mac meanwhile:
# another model run skews the timings. The Mac stays awake until it finishes. If it stops,
# run the same command again: finished steps are kept and skipped.
# Everything is synthetic and offline. Paste back the RESULTS.md it prints at the end.
set -euo pipefail

OUT="${OUT:-eval/out/speed_round2}"
MODELS="${MODELS:-eval/probe/models.local.json}"
CLAIMS="${CLAIMS:-C02,C05,C12}"   # the same three claims as the earlier Mac speed runs
RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
if [ "$RAM_GB" -gt 16 ]; then NCTX="${NCTX:-8192}"; else NCTX="${NCTX:-4096}"; fi

if ! python -c "import llama_cpp" 2>/dev/null; then
  echo "llama_cpp is not importable. Run 'source .venv/bin/activate' first, then try again."
  exit 1
fi
if [ ! -f "$MODELS" ]; then
  echo "$MODELS not found. Copy eval/probe/models.example.json there and list the 14B GGUF."
  exit 1
fi

ARGS=(--models "$MODELS" --claims "$CLAIMS" --n-ctx "$NCTX" --out "$OUT")
if [ -n "${MODEL:-}" ]; then ARGS+=(--model "$MODEL"); fi

KEEP_AWAKE=()
if command -v caffeinate >/dev/null; then KEEP_AWAKE=(caffeinate -ims); fi

"${KEEP_AWAKE[@]}" python -m eval.probe.speed_round2 "${ARGS[@]}"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md (printed above)."
