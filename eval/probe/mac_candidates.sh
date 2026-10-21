#!/usr/bin/env bash
# Mac run: newer local models against the signed probe set (eval/probe/candidates.py, 2026-10-20).
# Run from the repo root with the venv active:  bash eval/probe/mac_candidates.sh
# Downloads about 36 GB into ~/baker-models (MODELS_DIR) the first time, at pinned revisions,
# and checks each file's sha256. Everything after the download is synthetic and offline.
# Paste back the file it prints at the end. CANDIDATES="name ..." runs a subset.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-$HOME/baker-models}"
# A fresh folder per run: the probe appends to its call log, so a reused folder would mix runs.
OUT="${OUT:-eval/out/mac_candidates/$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$OUT" ]; then echo "$OUT already exists; set OUT to a new folder" >&2; exit 1; fi
NAMES="${CANDIDATES:-$(python -c 'from eval.probe.candidates import CANDIDATES; print(" ".join(c.name for c in CANDIDATES))')}"
mkdir -p "$OUT"

# The 27B needs more GPU memory than macOS allows by default on 24 GB (about two thirds of RAM).
# This raises the limit to 19 GB until the next restart. Close other apps during the run.
case " $NAMES " in
  *" qwen3.8-27b-ud-iq4_xs "*)
    if [ "${SKIP_SYSCTL:-0}" != "1" ]; then
      echo "Raising the GPU memory limit for the 27B (asks for your Mac password once)."
      sudo sysctl iogpu.wired_limit_mb=19456
    fi ;;
esac

python -m pip install -q "huggingface_hub>=0.34"
# Hugging Face's Xet transfer failed mid-file on the Mac (2026-10-21, "CAS Client Error"); the
# plain HTTP download resumes a partial file instead. HF_HUB_DISABLE_XET=0 turns Xet back on.
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
# A finished file is skipped (its sha256 is checked), so each retry only fetches what is missing.
for attempt in 1 2 3; do
  # shellcheck disable=SC2086
  python -m eval.probe.candidates download --dir "$MODELS_DIR" $NAMES && break
  if [ "$attempt" = 3 ]; then
    echo "The download failed 3 times. Run the same command again to pick up where it stopped." >&2
    exit 1
  fi
  echo "The download stopped (try $attempt of 3); trying again in 30 seconds." >&2
  sleep 30
done

{
  echo "commit $(git rev-parse --short HEAD)"
  python -c "import llama_cpp, platform; print('llama-cpp-python', llama_cpp.__version__, platform.platform())"
  echo "$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB"
  echo "gpu wired limit $(sysctl -n iogpu.wired_limit_mb 2>/dev/null || echo n/a) MB (0 = macOS default)"
} > "$OUT/versions.txt"

# A model that fails to load is recorded as a load error and the run moves on to the next one.
for name in $NAMES; do
  python -m eval.probe.candidates models-file "$name" --dir "$MODELS_DIR" --out "$OUT/$name.json"
  template="$(python -m eval.probe.candidates chat-template "$name")"
  for version in v1.1 v1.2; do
    prompt="$(python -c 'import sys; from eval.probe.candidates import PROMPTS; print(PROMPTS[sys.argv[1]])' "$version")"
    echo "$name, stance prompt $version (stance only, 1 answer per item)"
    python -m eval.probe.run_probe --models "$OUT/$name.json" --probe-set eval/gold/probe/probe.jsonl \
      --stance-only --repeat 1 --layout product_members --runtime flash --n-ctx 8192 \
      --chat-template "$template" --stance-prompt "$prompt" --out "$OUT/$name/$version" \
      || echo "$name $version stopped with an error; moving on" >&2
  done
done

python -m eval.probe.candidates verdict "$OUT" > /dev/null
{
  echo "# Mac results, newer local models on the signed probe ($(date -u +%Y-%m-%dT%H:%MZ))"
  echo
  cat "$OUT/versions.txt"
  echo
  cat "$OUT/VERDICT.md"
} > "$OUT/RESULTS.md"
echo
echo "Done. Paste back the contents of $OUT/RESULTS.md:"
echo
cat "$OUT/RESULTS.md"
