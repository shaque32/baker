#!/usr/bin/env bash
# The local model repeat check (eval/probe/repeat_check.py) on a rented AWS NVIDIA machine.
#
# Does the pinned 14B give the same answers when asked again on a cloud graphics card? Same
# stages as the Mac run (eval/probe/mac_repeat.sh): A the signed probe set twice, B a fresh
# load, C 20 items with no GPU offload, D two case01 audits. Synthetic and public data only.
#
# For an AWS g5.xlarge (A10G) or g6.xlarge (L4) running "Deep Learning Base OSS Nvidia Driver
# GPU AMI (Ubuntu 24.04)", 60 GB disk, logged in as ubuntu:
#
#   [ -d baker ] || git clone -q https://github.com/shaque32/baker.git
#   git -C baker checkout -q <the commit you were given>
#   bash baker/eval/probe/aws_repeat.sh          # starts in the background (about 2 hours)
#   bash baker/eval/probe/aws_repeat.sh status   # how far it is
#
# The result is ~/repeat-results.zip: the summary, every answer and what the machine is (AWS
# image, instance type, graphics card, driver, CUDA compiler). To compare two machines (two
# fresh instances, or AWS and the Mac):
#   python -m eval.probe.repeat_check --compare <first run folder> <second run folder>
# A stopped run starts the check over in a new folder; the runtime and model are kept.
set -eEuo pipefail  # -E: the ERR trap below also fires inside the setup functions

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${WORK:-$HOME/mabillon-run}"
LOG="$HOME/repeat.log"
PINS="${PINS:-$REPO/packaging/windows/pins.json}"
PY="$WORK/venv/bin/python"
RESULT="$HOME/repeat-results.zip"
export PIP_DISABLE_PIP_VERSION_CHECK=1
# Shut the machine down this many minutes after a finished run, so a forgotten machine stops
# billing for its graphics card. Its disk, and the result, stay until it is terminated.
STOP_AFTER_MIN="${STOP_AFTER_MIN:-180}"

if [ "${1:-}" = "status" ]; then
  if [ -f "$RESULT" ]; then
    echo "FINISHED. Copy ~/repeat-results.zip to your computer."
  elif [ -f "$WORK/.repeat.lock" ] && ! flock -n "$WORK/.repeat.lock" true; then
    echo "RUNNING. Latest lines:"
  else
    echo "NOT RUNNING and not finished. Send the lines below; running the start command again starts over."
  fi
  tail -n 6 "$LOG" 2> /dev/null || echo "(no log yet at $LOG)"
  exit 0
fi

# Detach, so closing the terminal does not stop the run.
if [ -z "${MABILLON_RUN_CHILD:-}" ]; then
  MABILLON_RUN_CHILD=1 nohup setsid bash "${BASH_SOURCE[0]}" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "Started. It runs on its own for about 2 hours; you can close this window."
  echo "To check on it later:  bash baker/eval/probe/aws_repeat.sh status"
  exit 0
fi

mkdir -p "$WORK"
exec 9> "$WORK/.repeat.lock"
flock -n 9 || { echo "another repeat check is already going"; exit 1; }
say() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
die() { say "STOPPED: $*"; exit 1; }
# shellcheck source=../aws_setup.sh
. "$REPO/eval/aws_setup.sh"
trap 'say "STOPPED at line $LINENO. Run the start command again, or send these lines."' ERR
if [ -f "$RESULT" ]; then
  mv "$RESULT" "$HOME/repeat-results-earlier-$(date -u +%Y%m%dT%H%M%SZ).zip"
  say "kept the earlier result as $(ls -t "$HOME"/repeat-results-earlier-*.zip | head -n 1)"
fi

say "1/5 checking the machine (Mabillon $(git -C "$REPO" describe --tags --always --dirty))"
nvidia-smi -L || die "no NVIDIA graphics card found; this needs a g5 or g6 machine with the NVIDIA AMI"
free_gb=$(df --output=avail -BG "$WORK" | tail -n 1 | tr -dc 0-9)
need_gb=5  # the runtime build and the results
[ -f "$WORK/models/$(pin model.file)" ] || need_gb=$((need_gb + $(pin model.size) / 1000000000 + 1))
[ "$free_gb" -ge "$need_gb" ] || die "only ${free_gb} GB free, need ${need_gb} GB; make the disk 60 GB"

say "2/5 installing Python 3.12 and Mabillon"
aws_install
aws_build_runtime "3/5"
aws_get_model "4/5"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$WORK/repeat/$STAMP"
MODELS="$WORK/repeat-models.json"
"$PY" -c 'import json, sys
json.dump([{"name": sys.argv[1], "path": sys.argv[2], "sha256": sys.argv[3], "license": sys.argv[4]}],
          open(sys.argv[5], "w"), indent=2)' \
  "$(pin model.name)" "$MODEL" "$(pin model.sha256)" "$(pin model.license)" "$MODELS"
aws_host_json "$WORK/host-$STAMP.json"

say "5/5 running the repeat check (about 2 hours; one line per answer)"
cd "$REPO"
status=0
"$PY" -m eval.probe.repeat_check --models "$MODELS" --out "$OUT" --host "$WORK/host-$STAMP.json" \
  ${STAGES:+--stages "$STAGES"} || status=$?
cp "$WORK/host-$STAMP.json" "$OUT/host.json"
(cd "$WORK/repeat" && "$PY" -m zipfile -c "$RESULT" "$STAMP")
if [ "$status" -ne 0 ]; then
  say "A stage failed (exit $status); the summary in ~/repeat-results.zip is partial."
fi
cat "$OUT/summary.md" || true
say "FINISHED. Copy ~/repeat-results.zip to your computer."
say "This machine shuts itself down in $STOP_AFTER_MIN minutes; terminate it once you have the file."
sudo -n shutdown -h "+$STOP_AFTER_MIN" > /dev/null 2>&1 || true
