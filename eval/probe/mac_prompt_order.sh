#!/usr/bin/env bash
# Stance prompt v1.1 draft vs the signed v1.0, on a Mac: same words, fixed text first.
# Run from the repo root with the venv active:  bash eval/probe/mac_prompt_order.sh
# Needs eval/probe/models.local.json (the same file mac_wave3.sh uses). To time one model only,
# point MODELS at a file listing just that model (for example the 14B).
# Everything is synthetic and offline. Paste back the file it prints at the end.
#
# 1. The stance probe on the signed set, once per prompt (accuracy: the four "Expert confirms"
#    bars must hold for v1.1 before Arsh signs it).
# 2. The timed audit on the same claims, once per prompt (speed: seconds per stance call).
# SKIP_SIGNED=1 skips the v1.0 runs, if you already have them from this machine.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
if [ -f eval/gold/probe/probe.jsonl ]; then DEFAULT_PROBE=eval/gold/probe/probe.jsonl
else DEFAULT_PROBE=eval/probe_draft/probe_draft.jsonl; fi
PROBE_SET="${PROBE_SET:-$DEFAULT_PROBE}"
OUT="${OUT:-eval/out/prompt_order_mac}"
DRAFT=eval/probe/stance_v1_1_draft.md
SIGNED=core/audit/prompts/stance.md
RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
if [ "$RAM_GB" -gt 16 ]; then NCTX="${NCTX:-8192}"; else NCTX="${NCTX:-4096}"; fi
CLAIMS="${CLAIMS:-C02,C05,C12}"   # the same three claims as the earlier Mac speed runs

mkdir -p "$OUT"
python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())" \
  > "$OUT/versions.txt"

run_pair() {  # $1 label, $2 prompt file
  echo "probe, stance only, prompt $1"
  python -m eval.probe.run_probe --models "$MODELS" --probe-set "$PROBE_SET" --stance-only \
    --repeat 1 --n-ctx "$NCTX" --stance-prompt "$2" --out "$OUT/probe_$1"
  echo "timed audit of $CLAIMS, prompt $1"
  python -m eval.probe.time_case --models "$MODELS" --n-ctx "$NCTX" --claims "$CLAIMS" \
    --stance-prompt "$2" --out "$OUT/speed_$1"
}

if [ "${SKIP_SIGNED:-0}" != "1" ]; then run_pair v1_0 "$SIGNED"; fi
run_pair v1_1 "$DRAFT"

{
  echo "# Stance prompt order, Mac ($(date -u +%Y-%m-%dT%H:%MZ), ${RAM_GB} GB, n_ctx ${NCTX})"
  echo
  cat "$OUT/versions.txt"
  for v in v1_0 v1_1; do
    [ -f "$OUT/probe_$v/summary.md" ] || continue
    echo; echo "## Prompt $v"; echo
    cat "$OUT/probe_$v/summary.md"; echo
    cat "$OUT/speed_$v/summary.md"
  done
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
