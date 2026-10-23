#!/usr/bin/env bash
# Mac run for stance prompt v1.3, the local 14B's rules 12 and 23 fix (eval/probe/v13/PREREGISTERED.md).
# Run from the repo root with the venv active:  bash eval/probe/mac_v13.sh
# Needs eval/probe/models.local.json with the 14B (the file the earlier Mac runs used).
# Everything is synthetic and offline. One answer per item, about 25 to 35 s each on a 24 GB
# MacBook Air: about 2.5 hours, or about 4.5 if v1.3b has to run too.
# To resume after a stop, run it again with OUT set to the same folder: finished steps are kept.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
OUT="${OUT:-eval/out/mac_v13/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
if [ ! -f "$OUT/model.json" ]; then
  python -c 'import json, sys; from eval.bench.fair_steps import pick_entry
json.dump([pick_entry(json.load(open(sys.argv[1])), sys.argv[2] or None)], open(sys.argv[3], "w"), indent=2)' \
    "$MODELS" "${MODEL_NAME:-}" "$OUT/model.json"
fi
{
  echo "commit $(git rev-parse --short HEAD)"
  python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())"
  echo "$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
} >> "$OUT/versions.txt"

# macOS ships bash 3.2, which has no associative arrays.
prompt_file() {
  case "$1" in
    base) echo eval/probe/stance_v1_1_signed.md ;;
    a) echo eval/probe/stance_v1_3a_draft.md ;;
    b) echo eval/probe/stance_v1_3b_draft.md ;;
  esac
}
set_file() {
  case "$1" in
    signed) echo eval/gold/probe/probe.jsonl ;;
    fresh) echo eval/probe/v13/heldout.jsonl ;;
    tf24) echo eval/probe/v13/told_frame_24.jsonl ;;
    r26) echo eval/probe/v13/rules_12_23_26.jsonl ;;
  esac
}

# One prompt on one set. A finished step (summary.json written) is skipped; a half-finished one
# starts over, since the probe appends to its call log.
step() {
  local p="$1" s="$2" dir="$OUT/$1_$2"
  # Done means a call log and a summary with no load error; a step whose model failed to load
  # wrote a summary but no calls, and runs again.
  if [ -f "$dir/summary.json" ] && ls "$dir"/*.calls.jsonl > /dev/null 2>&1 \
    && ! grep -q '"load_error"' "$dir/summary.json"; then
    echo "  $1_$2 already done"; return
  fi
  rm -rf "$dir"
  echo "  $1_$2: $(prompt_file "$p") on $(set_file "$s")"
  python -m eval.probe.run_probe --models "$OUT/model.json" --probe-set "$(set_file "$s")" \
    --stance-only --repeat 1 --layout product_members --stance-prompt "$(prompt_file "$p")" \
    --out "$dir" > /dev/null
}

echo "1/3 v1.1, the 14B's own prompt, on the three new sets (the baseline)"
for s in fresh tf24 r26; do step base "$s"; done
# On the signed set the baseline is the Mac run of 2026-10-19, but only for the same model file
# and the same prompts byte for byte; otherwise v1.1 runs on it here.
if ! python -m eval.probe.v13.score baseline-ok "$OUT"; then step base signed; fi

echo "2/3 v1.3a on all four sets"
for s in signed fresh tf24 r26; do step a "$s"; done

if python -m eval.probe.v13.score decide "$OUT" a; then
  echo "3/3 v1.3a meets every criterion, so v1.3b does not run (PREREGISTERED.md)"
else
  echo "3/3 v1.3a does not meet every criterion: v1.3b on all four sets"
  for s in signed fresh tf24 r26; do step b "$s"; done
fi

{
  echo "# Mac results, stance v1.3 re-probe ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo
  cat "$OUT/versions.txt"
  echo
  python -m eval.probe.v13.score report "$OUT"
} > "$OUT/RESULTS.md"
echo
echo "Done. Upload the folder $OUT, or paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
