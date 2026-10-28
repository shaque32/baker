#!/usr/bin/env bash
# Install Mabillon on an Apple silicon Mac, for one person, with no administrator password.
#
#   bash packaging/mac/install.sh            # from the unzipped Mabillon folder
#   bash packaging/mac/install.sh --no-model # skip the 9 GB model download (copy it in later)
#
# What it does, in order (docs/install-mac.md explains each step in plain words):
#   1. checks the Mac: Apple silicon, memory, disk space
#   2. checks Apple's command line tools (needed once, to build the model runtime)
#   3. installs uv (a Python installer) if it is missing, then Python 3.12 inside ~/Mabillon/app
#   4. copies Mabillon to ~/Mabillon/app/baker and installs it with the local model runtime (Metal)
#   5. downloads the model (Qwen3-14B Q4, 9 GB) to ~/Mabillon/models and checks its SHA-256
#   6. writes ~/.mabillon/model.json (only if there is no model setting), runs the model check and
#      builds the demo case, and puts two launchers on the Desktop: "Mabillon" and "Mabillon demo"
# A Mac set up when the product was called Baker keeps what it has: a verified model in
# ~/Baker/models and a model setting in ~/.baker/model.json are used where they are, and the
# Desktop launchers "Baker" and "Baker demo" this installer made are replaced.
# Downloads happen only here, at install time. Mabillon itself makes no network calls, except for a
# case the expert opts in to cloud AI (stance questions to Anthropic, on the expert's own key).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP="$HOME/Mabillon/app"
MODELS="$HOME/Mabillon/models"
OLD_MODELS="$HOME/Baker/models"  # where the Baker installer put the model
# MABILLON_PINS and MABILLON_MIN_MEMORY_GB (BAKER_* still read) are for the clean-install test
# only (.github/workflows/clean-install.yml): a stub model on a small CI Mac.
PINS="${MABILLON_PINS:-${BAKER_PINS:-$HERE/packaging/windows/pins.json}}"
MIN_GB="${MABILLON_MIN_MEMORY_GB:-${BAKER_MIN_MEMORY_GB:-16}}"
WANT_MODEL=1
for arg in "$@"; do
  case "$arg" in
    --no-model) WANT_MODEL=0 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

# Bold step titles and a plain finish, like the app; no colour codes when output is not a terminal.
if [ -t 1 ]; then B=$'\033[1m' R=$'\033[0m'; else B="" R=""; fi
say() { printf '\n%s%s%s\n' "$B" "$*" "$R"; }
stop() { printf '\n%sStopped:%s %s\n' "$B" "$R" "$*"; exit 1; }
# One pinned value from pins.json (the Windows build's pins: the same runtime and model).
pin() { "$APP/.venv/bin/python" -c "import json, sys; print(json.load(open(sys.argv[1]))$1)" "$PINS"; }

[ -f "$HERE/pyproject.toml" ] && [ -d "$HERE/core" ] || stop "run this from the Mabillon folder"

say "Step 1 of 6: Checking this Mac"
[ "$(uname -s)" = "Darwin" ] || stop "this installer is for a Mac; on Windows use Mabillon-Setup.exe"
[ "$(uname -m)" = "arm64" ] || stop "Mabillon needs an Apple silicon Mac (M1 or later)"
RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 ))
FREE_GB=$(( $(df -k "$HOME" | awk 'NR==2 {print $4}') / 1048576 ))
echo "Memory: ${RAM_GB} GB. Free disk: ${FREE_GB} GB."
if [ "$RAM_GB" -lt "$MIN_GB" ]; then
  stop "Mabillon's model needs at least $MIN_GB GB of memory; this Mac has ${RAM_GB} GB"
elif [ "$RAM_GB" -lt 24 ]; then
  echo "NOTE: with ${RAM_GB} GB a case runs, but slowly. 24 GB or more is recommended."
fi
NEED_GB=3; [ "$WANT_MODEL" = 1 ] && NEED_GB=15
[ "$FREE_GB" -ge "$NEED_GB" ] || stop "needs ${NEED_GB} GB free disk; ${FREE_GB} GB free"

say "Step 2 of 6: Apple command line tools"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  stop "a window asks to install Apple's command line tools. Click Install, wait until it
finishes (10 to 20 minutes), then run this installer again."
fi
echo "Installed."

say "Step 3 of 6: Python"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (from astral.sh) into ~/.local/bin"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
command -v uv >/dev/null 2>&1 || stop "uv did not install; check the internet connection"
mkdir -p "$APP"
[ -x "$APP/.venv/bin/python" ] || uv venv --python 3.12 "$APP/.venv"

say "Step 4 of 6: Mabillon and the model runtime (building it takes 5 to 10 minutes)"
if [ "$HERE" != "$APP/baker" ]; then
  mkdir -p "$APP/baker"
  rsync -a --delete --exclude .git --exclude .venv --exclude 'eval/out' \
    --exclude 'eval/synthetic/case02*' --exclude 'eval/gold/case02' "$HERE/" "$APP/baker/"
  # The copy has no .git, so record the commit it came from and whether the copied tracked
  # files differed from it (rsync copies uncommitted edits too); reports stamp both (core/build.py).
  if COMMIT="$(git -C "$HERE" rev-parse HEAD 2>/dev/null)"; then
    DIRTY=false
    [ -n "$(git -C "$HERE" status --porcelain --untracked-files=no)" ] && DIRTY=true
    printf '{"git_commit": "%s", "dirty": %s}\n' "$COMMIT" "$DIRTY" > "$APP/baker/BUILD_INFO.json"
  fi
fi
LLAMA_VERSION="$(pin "['llama_cpp_python']['version']")"
CMAKE_ARGS="-DGGML_METAL=on" uv pip install --python "$APP/.venv/bin/python" \
  -e "$APP/baker[synthetic,local,cloud]" "llama-cpp-python==$LLAMA_VERSION"
MABILLON="$APP/.venv/bin/mabillon"
"$MABILLON" --help >/dev/null || stop "Mabillon did not install"
echo "Installed Mabillon in $APP."

MODEL_FILE="$(pin "['model']['file']")"
MODEL_SHA="$(pin "['model']['sha256']")"
MODEL_URL="$(pin "['model']['url']")"
MODEL_NAME="$(pin "['model']['name']")"
CONFIG="$HOME/.mabillon/model.json"
OLD_CONFIG="$HOME/.baker/model.json"  # Mabillon reads it while there is no new one
# A model the Baker installer downloaded stays where it is (checked below like any other). So
# does its destination while its model setting is the one kept: after `--no-model` that setting
# already names ~/Baker/models, and the model has to arrive there.
if [ ! -f "$MODELS/$MODEL_FILE" ]; then
  if [ -f "$OLD_MODELS/$MODEL_FILE" ] || { [ ! -f "$CONFIG" ] && [ -f "$OLD_CONFIG" ]; }; then
    MODELS="$OLD_MODELS"
  fi
fi
MODEL_PATH="$MODELS/$MODEL_FILE"

say "Step 5 of 6: The model ($MODEL_FILE, about 9 GB)"
if [ -f "$MODEL_PATH" ] && [ "$(shasum -a 256 "$MODEL_PATH" | cut -d' ' -f1)" = "$MODEL_SHA" ]; then
  echo "Already here, SHA-256 checked."
elif [ "$WANT_MODEL" = 1 ]; then
  mkdir -p "$MODELS"
  echo "Downloading from Hugging Face. If it stops, run the installer again: it resumes."
  curl -L --fail -C - -o "$MODEL_PATH.part" "$MODEL_URL"
  echo "Checking the file's SHA-256 (a minute or two)"
  GOT="$(shasum -a 256 "$MODEL_PATH.part" | cut -d' ' -f1)"
  if [ "$GOT" != "$MODEL_SHA" ]; then
    rm -f "$MODEL_PATH.part"
    stop "the download's SHA-256 is $GOT, not $MODEL_SHA; it was deleted. Run again."
  fi
  mv "$MODEL_PATH.part" "$MODEL_PATH"
else
  echo "Skipped. Copy $MODEL_FILE into $MODELS later and run the installer again."
fi

say "Step 6 of 6: Settings, checks and launchers"
if [ -f "$CONFIG" ]; then
  echo "Keeping the model setting you already have: $CONFIG"
elif [ -f "$OLD_CONFIG" ]; then
  echo "Keeping the model setting you already have: $OLD_CONFIG"
else
  mkdir -p "$HOME/.mabillon"
  printf '{\n  "name": "%s",\n  "path": "%s",\n  "sha256": "%s",\n  "n_ctx": 8192\n}\n' \
    "$MODEL_NAME" "$MODEL_PATH" "$MODEL_SHA" > "$CONFIG"
  echo "Wrote $CONFIG"
fi
"$MABILLON" model-check || echo "The model is not ready yet; Mabillon works, but cannot audit a case."
"$MABILLON" demo --build-only

mkdir -p "$HOME/Desktop"
for name in "Mabillon" "Mabillon demo"; do
  cmd="serve --open"; [ "$name" = "Mabillon demo" ] && cmd="demo"
  f="$HOME/Desktop/$name.command"
  printf '#!/bin/bash\n# Opens %s in your browser. Close this window to stop it.\n"%s" %s\n' \
    "$name" "$MABILLON" "$cmd" > "$f"
  chmod +x "$f"
done
# The launchers the Baker installer made, and only those (they open with its comment line).
for name in "Baker" "Baker demo"; do
  f="$HOME/Desktop/$name.command"
  if [ -f "$f" ] && sed -n 2p "$f" | grep -q "^# Opens $name in your browser"; then
    rm -f "$f"
    echo "Replaced the Desktop launcher \"$name\" with \"${name/Baker/Mabillon}\"."
  fi
done

say "Mabillon is installed."
cat <<EOF
Double-click "Mabillon" on your Desktop to open your cases, or "Mabillon demo" for the demo case.
Mabillon opens in your browser at http://127.0.0.1 and runs only on this Mac.
Close the Terminal window that opens with it to stop Mabillon.
EOF
if [ -d "$HOME/Baker/app" ]; then
  echo
  echo "The program the Baker installer put in ~/Baker/app is no longer used. You can delete that"
  echo "folder; your cases, the model and its setting stay where they are."
fi
