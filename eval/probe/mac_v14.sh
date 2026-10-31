#!/usr/bin/env bash
# Mac run for stance prompt v1.4, the signed v1.1 wording with the fixed instructions first, so
# llama.cpp can reuse them between calls (eval/probe/v14/PREREGISTERED.md).
#
#   cd ~/baker && source .venv/bin/activate
#   bash eval/probe/mac_v14.sh
#
# Needs eval/probe/models.local.json with the 14B (the file the earlier Mac runs used). Run
# nothing else on the Mac meanwhile: another model run skews the timings. About 3 to 4 hours
# on a 24 GB MacBook Air; the Mac stays awake until it finishes. To resume after a stop, run it
# again with OUT set to the same folder: finished steps are kept.
# Everything is synthetic and offline. Paste back the RESULTS.md it prints at the end.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
OUT="${OUT:-eval/out/mac_v14/$(date -u +%Y%m%dT%H%M%SZ)}"
CLAIMS="C02,C05,C12"  # the claims speed round 2 timed (PREREGISTERED.md)
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
mkdir -p "$OUT"
if [ ! -f "$OUT/model.json" ]; then
  python -c 'import json, sys; from eval.bench.fair_steps import pick_entry
json.dump([pick_entry(json.load(open(sys.argv[1])), sys.argv[2] or None)], open(sys.argv[3], "w"), indent=2)' \
    "$MODELS" "${MODEL_NAME:-}" "$OUT/model.json"
fi
{
  echo "commit $(git rev-parse --short HEAD)"
  python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())"
  echo "$RAM_GB GB"
} >> "$OUT/versions.txt"

KEEP_AWAKE=()
if command -v caffeinate >/dev/null; then KEEP_AWAKE=(caffeinate -ims); fi

# macOS ships bash 3.2, which has no associative arrays.
prompt_file() {
  case "$1" in
    base) echo eval/probe/stance_v1_1_signed.md ;;
    v14) echo eval/probe/stance_v1_4_draft.md ;;
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

# One prompt on one set. A finished step (a call log and a summary with no load error) is
# skipped; a half-finished one starts over, since the probe appends to its call log.
probe() {
  local p="$1" s="$2" dir="$OUT/$1_$2"
  if [ -f "$dir/summary.json" ] && ls "$dir"/*.calls.jsonl > /dev/null 2>&1 \
    && ! grep -q '"load_error"' "$dir/summary.json"; then
    echo "  $1_$2 already done"; return
  fi
  rm -rf "$dir"
  echo "  $1_$2: $(prompt_file "$p") on $(set_file "$s")"
  "${KEEP_AWAKE[@]}" python -m eval.probe.run_probe --models "$OUT/model.json" \
    --probe-set "$(set_file "$s")" --stance-only --repeat 1 --layout product_members \
    --stance-prompt "$(prompt_file "$p")" --n-ctx "$NCTX" --out "$dir" > /dev/null
}

# One timed audit of the three claims, the product's wiring on the given prompt.
audit() {
  local p="$1" dir="$OUT/time_$1"
  if [ -f "$dir/summary.json" ] && grep -q '"cold"' "$dir/summary.json"; then
    echo "  time_$1 already done"; return
  fi
  rm -rf "$dir"
  echo "  time_$1: case01 $CLAIMS with $(prompt_file "$p")"
  local extra=()
  if [ "$p" = v14 ]; then extra=(--stance-prompt "$(prompt_file "$p")"); fi
  "${KEEP_AWAKE[@]}" python -m eval.probe.time_case --models "$OUT/model.json" --claims "$CLAIMS" \
    --n-ctx "$NCTX" --out "$dir" "${extra[@]+"${extra[@]}"}" > /dev/null
}

echo "1/4 v1.1, the signed prompt, on the four sets"
for s in signed fresh tf24 r26; do probe base "$s"; done
echo "2/4 v1.4, the same words with the instructions first, on the four sets"
for s in signed fresh tf24 r26; do probe v14 "$s"; done
echo "3/4 timed audit with v1.1"
audit base
echo "4/4 timed audit with v1.4"
audit v14

{
  echo "# Mac results, stance v1.4 test ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo
  cat "$OUT/versions.txt"
  echo
  python -m eval.probe.v14.score report "$OUT"
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
