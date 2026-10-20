#!/usr/bin/env bash
# Mac run: does the local stance model give the same output when asked again? (2026-10-20)
# Run from the repo root with the venv active:  bash eval/probe/mac_repeat.sh
# Needs eval/probe/models.local.json with the 14B (the file the earlier Mac runs used); set
# MODEL_NAME to repeat-check another entry. About 3.7 hours on the 14B (an estimate from the
# 2026-10-12 speed run; the CPU-only stage is a guess). Keep the Mac awake and plugged in.
# Everything is synthetic and offline. Paste back the file it prints at the end.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
OUT="${OUT:-eval/out/repeat/$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$OUT" ]; then echo "$OUT already exists; set OUT to a new folder" >&2; exit 1; fi

python -m eval.probe.repeat_check --dry-run
caffeinate -dimsu python -m eval.probe.repeat_check --models "$MODELS" \
  ${MODEL_NAME:+--model "$MODEL_NAME"} --chat-template "${CHAT_TEMPLATE:-gguf}" --out "$OUT" || true

echo
echo "Done. Paste back the contents of $OUT/summary.md:"
echo
cat "$OUT/summary.md"
