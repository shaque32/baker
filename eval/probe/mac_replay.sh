#!/usr/bin/env bash
# Mac run for the shorter-context replay (eval/probe/REPLAY_PREREGISTERED.md): the recorded
# case04 stance calls again, first with 20 and then with 8 messages either side of the record.
#
#   cd ~/baker && source .venv/bin/activate
#   bash eval/probe/mac_replay.sh
#
# Needs eval/probe/models.local.json with the 14B that the case04 run used, and that run's
# database (eval/out/case04/rubber_stamp/testability/case04.db by default; set DB for another
# path). Run nothing else on the Mac meanwhile. About 4 hours on a 24 GB MacBook Air (estimated
# from the case04 run's 46 s per stance call); the Mac stays awake until it finishes. To resume
# after a stop, run it again with OUT set to the same folder: each replay resumes where it
# stopped, and only as the same replay (another model file, setting, prompt or code is refused).
# Everything is synthetic and offline. Paste back the RESULTS.md it prints at the end.
set -euo pipefail

MODELS="${MODELS:-eval/probe/models.local.json}"
DB="${DB:-eval/out/case04/rubber_stamp/testability/case04.db}"
OUT="${OUT:-eval/out/mac_replay/$(date -u +%Y%m%dT%H%M%SZ)}"
GOLD=eval/gold/case04/gold.jsonl
SAMPLE=2  # every second assumption (REPLAY_PREREGISTERED.md)
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
if [ ! -f "$DB" ]; then
  echo "$DB not found. Set DB to the case04.db of the 2026-10-29 go/no-go run, then try again."
  exit 1
fi
mkdir -p "$OUT"
{
  echo "commit $(git rev-parse --short HEAD)"
  python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())"
  echo "$RAM_GB GB, n_ctx $NCTX, database $DB"
} >> "$OUT/versions.txt"

KEEP_AWAKE=()
if command -v caffeinate >/dev/null; then KEEP_AWAKE=(caffeinate -ims); fi

echo "1/3 rebuild check (no model)"
python -m eval.probe.replay check --db "$DB" > "$OUT/check.json"

replay() {
  local prompt="$1" window="$2" dir="$OUT/$1_w$2"
  echo "  ${prompt}_w${window}: $window messages either side"
  "${KEEP_AWAKE[@]}" python -m eval.probe.replay run --db "$DB" --models "$MODELS" \
    ${MODEL_NAME:+--model "$MODEL_NAME"} --prompt "$prompt" --window "$window" \
    --sample "$SAMPLE" --n-ctx "$NCTX" --out "$dir" > /dev/null
}

echo "2/3 the signed prompt, 20 messages either side (the recorded audit)"
replay signed 20
echo "3/3 the signed prompt, 8 messages either side"
replay signed 8

{
  echo "# Mac results, shorter-context replay ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo
  cat "$OUT/versions.txt"
  echo
  python -m eval.probe.replay report "$OUT" --gold "$GOLD"
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
