#!/usr/bin/env bash
# validation-v1 on a rented NVIDIA machine (eval/validation/PREREGISTERED.md).
#
# For an AWS g5.xlarge (or g6.xlarge) running "Deep Learning Base OSS Nvidia Driver GPU AMI
# (Ubuntu 24.04)", logged in as ubuntu, with the claims file copied to the home folder:
#
#   [ -d baker ] || git clone -q -b validation-v1-run2 https://github.com/shaque32/baker.git
#   (run 2, eval/validation/PREREGISTERED_v2.md; run 1 used validation-v1)
#   bash baker/eval/validation/aws_run.sh          # starts the run in the background
#   bash baker/eval/validation/aws_run.sh status   # how far it is
#
# It installs Python 3.12 and Mabillon, builds the CUDA llama-cpp-python pinned in
# packaging/windows/pins.json, downloads the pinned model and the public iOS 15 phone and checks
# both by SHA-256, then runs eval/validation/hickman_run.py. The result is ~/results.zip.
# Everything it fetches is public; the claims file holds claims only, no answers.
# Run it again after any stop: finished steps are kept and the audit resumes.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${WORK:-$HOME/mabillon-run}"
LOG="$HOME/run.log"
CLAIMS="${CLAIMS:-$HOME/validation-claims-ios15.jsonl}"
# The pinned inputs. The overrides exist only to test the script on a small synthetic package.
CLAIMS_SHA="${CLAIMS_SHA:-ee0f124479ce6ebe449723ed8dd1a04c81d653ba300f892feaa284fc5fc068be}"
UFDR_URL="${UFDR_URL:-https://digitalcorpora.s3.amazonaws.com/corpora/mobile/android_13/ios_15_3_1/iOS_15_Public_Image_Reader.tar.gz}"
UFDR_MEMBER="${UFDR_MEMBER:-iOS_15_Public_Image_Reader/iPhone 8/iOS_15_Public_Image.ufdr}"
UFDR_SIZE="${UFDR_SIZE:-30705362520}"
REPORT_SHA="${REPORT_SHA:-bf9bab624cebb7cd32d8543d0db60894b587597ae03d8ec97375862050ec7b8d}"
PINS="${PINS:-$REPO/packaging/windows/pins.json}"
UFDR="$WORK/phone/$(basename "$UFDR_MEMBER")"
OUT="$WORK/out-setup2"  # a new folder for each hickman_run.SETUP; run 1 used $WORK/out
PY="$WORK/venv/bin/python"
export PIP_DISABLE_PIP_VERSION_CHECK=1
# Shut the machine down this many minutes after a finished run, so a forgotten machine stops
# billing for its graphics card. Its disk, and ~/results.zip, stay until it is terminated.
STOP_AFTER_MIN="${STOP_AFTER_MIN:-180}"

if [ "${1:-}" = "status" ]; then
  if [ -f "$HOME/results.zip" ]; then
    echo "FINISHED. Copy ~/results.zip to your computer (guide, Part 5)."
  elif [ -f "$WORK/.lock" ] && ! flock -n "$WORK/.lock" true; then
    echo "RUNNING. Latest lines:"
  else
    echo "NOT RUNNING and not finished. Send the lines below; running the start command again resumes."
  fi
  tail -n 6 "$LOG" 2> /dev/null || echo "(no log yet at $LOG)"
  exit 0
fi

# Detach, so closing the terminal does not stop the run.
if [ -z "${MABILLON_RUN_CHILD:-}" ]; then
  MABILLON_RUN_CHILD=1 nohup setsid bash "${BASH_SOURCE[0]}" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "Started. It runs on its own for several hours; you can close this window."
  echo "To check on it later:  bash baker/eval/validation/aws_run.sh status"
  exit 0
fi

mkdir -p "$WORK/phone" "$WORK/models" "$WORK/sdist"
exec 9> "$WORK/.lock"
flock -n 9 || { echo "another run is already going"; exit 1; }
say() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
die() { say "STOPPED: $*"; exit 1; }
pin() { python3 -c 'import json, sys; d = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d = d[k]
print(d)' "$PINS" "$1"; }
trap 'say "STOPPED at line $LINENO. Run the start command again to resume, or send these lines."' ERR
if [ -f "$HOME/results.zip" ] && [ ! -f "$OUT/results.zip" ]; then
  # An earlier run's results: kept under another name, so status does not report this run done.
  mv "$HOME/results.zip" "$HOME/results-earlier-$(date -u +%Y%m%dT%H%M%SZ).zip"
  say "kept the earlier run's results as $(ls -t "$HOME"/results-earlier-*.zip | head -n 1)"
fi

say "1/6 checking the machine (Mabillon $(git -C "$REPO" describe --tags --always))"
nvidia-smi -L || die "no NVIDIA graphics card found; this needs a g5 or g6 machine with the NVIDIA AMI"
[ -f "$CLAIMS" ] || die "no claims file at $CLAIMS; copy it to the home folder first (guide, Part 3)"
echo "$CLAIMS_SHA  $CLAIMS" | sha256sum -c --quiet || die "$CLAIMS is not the expected claims file"
free_gb=$(df --output=avail -BG "$WORK" | tail -n 1 | tr -dc 0-9)
need_gb=5  # the case database, the runtime build and the results
[ -f "$UFDR" ] || need_gb=$((need_gb + UFDR_SIZE / 1000000000 + 1))
[ -f "$WORK/models/$(pin model.file)" ] || need_gb=$((need_gb + $(pin model.size) / 1000000000 + 1))
[ "$free_gb" -ge "$need_gb" ] || die "only ${free_gb} GB free, need ${need_gb} GB; make the disk 200 GB"

say "2/6 installing Python 3.12 and Mabillon"
if [ ! -x "$PY" ]; then
  command -v uv > /dev/null || [ -x "$HOME/.local/bin/uv" ] || curl -LsSf https://astral.sh/uv/install.sh | sh
  "$HOME/.local/bin/uv" venv -q --seed --python 3.12 "$WORK/venv" 2> /dev/null \
    || uv venv -q --seed --python 3.12 "$WORK/venv"
fi
"$PY" -m pip install -q -e "$REPO[synthetic]"

llama_version=$(pin llama_cpp_python.version)
if ! "$PY" -c 'import sys, llama_cpp
sys.exit(0 if llama_cpp.__version__ == sys.argv[1] and llama_cpp.llama_supports_gpu_offload() else 1)' \
  "$llama_version" 2> /dev/null; then
  say "3/6 building the model runtime for the graphics card (about 15 minutes)"
  "$PY" -m pip download -q --no-deps --no-binary :all: "llama-cpp-python==$llama_version" -d "$WORK/sdist"
  sdist=$(ls "$WORK"/sdist/llama_cpp_python-*.tar.gz | head -n 1)
  echo "$(pin llama_cpp_python.sdist_sha256)  $sdist" | sha256sum -c --quiet \
    || die "$sdist is not the pinned llama-cpp-python source"
  CUDACXX=/usr/local/cuda/bin/nvcc
  [ -x "$CUDACXX" ] || CUDACXX=$(ls /usr/local/cuda-*/bin/nvcc 2> /dev/null | sort -V | tail -n 1)
  [ -x "$CUDACXX" ] || die "no CUDA compiler found; use the Deep Learning Base OSS Nvidia Driver AMI"
  export CUDACXX PATH="$(dirname "$CUDACXX"):$PATH"
  CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86-real;89" FORCE_CMAKE=1 \
    CMAKE_BUILD_PARALLEL_LEVEL="$(nproc)" "$PY" -m pip install -q --no-cache-dir "$sdist"
  "$PY" -c 'import llama_cpp, sys; sys.exit(0 if llama_cpp.llama_supports_gpu_offload() else 1)' \
    || die "the model runtime was built without graphics card support"
else
  say "3/6 model runtime already built"
fi

model="$WORK/models/$(pin model.file)"
if [ ! -f "$model" ]; then
  say "4/6 downloading the AI model (9 GB)"
  curl -fL --retry 5 -C - -s -o "$model.part" "$(pin model.url)"
  echo "$(pin model.sha256)  $model.part" | sha256sum -c --quiet || {
    rm -f "$model.part"
    die "the model download is damaged; run the start command again"
  }
  mv "$model.part" "$model"
else
  say "4/6 AI model already downloaded"
fi
export MABILLON_MODEL_CONFIG="$WORK/model.json"
"$PY" -c 'import json, sys
json.dump({"name": sys.argv[1], "path": sys.argv[2], "sha256": sys.argv[3], "n_ctx": int(sys.argv[4])},
          open(sys.argv[5], "w"), indent=2)' \
  "$(pin model.name)" "$model" "$(pin model.sha256)" "$(pin model.n_ctx)" "$MABILLON_MODEL_CONFIG"
"$WORK/venv/bin/mabillon" model-check || die "the model check failed"

if [ "$(stat -c %s "$UFDR" 2> /dev/null || echo 0)" != "$UFDR_SIZE" ]; then
  say "5/6 downloading the public test phone (15 GB, unpacks to 31 GB; about 20 minutes)"
  for try in 1 2 3; do
    rm -f "$UFDR"
    if curl -fsSL --retry 5 "$UFDR_URL" | tar -xzf - -C "$WORK/phone" --strip-components=2 "$UFDR_MEMBER" \
      && [ "$(stat -c %s "$UFDR")" = "$UFDR_SIZE" ]; then
      break
    fi
    [ "$try" = 3 ] && die "the phone download failed three times"
    say "   the download broke; trying again ($try of 3)"
  done
else
  say "5/6 test phone already downloaded"
fi

say "6/6 running the audit (several hours; one line per claim, 106 claims)"
cd "$REPO"
"$PY" -m eval.validation.hickman_run --ufdr "$UFDR" --claims "$CLAIMS" --out "$OUT" \
  --claims-sha256 "$CLAIMS_SHA" --report-sha256 "$REPORT_SHA" ${RUN_ARGS:-}
cp "$OUT/results.zip" "$HOME/results.zip"
say "FINISHED. Copy ~/results.zip to your computer (guide, Part 5)."
say "This machine shuts itself down in $STOP_AFTER_MIN minutes; terminate it once you have the file."
sudo -n shutdown -h "+$STOP_AFTER_MIN" > /dev/null 2>&1 || true
