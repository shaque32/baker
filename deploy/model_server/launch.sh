#!/usr/bin/env bash
# Start the Mabillon model server (plan C) on a rented 8-GPU machine. NOT for real cases yet:
# the app does not call this server until Arsh signs the CLAUDE.md network change, and the
# consensus conditions (pinned-stack stage 1 re-run, repeat check, held-out items) must pass
# first (/mnt/project-files/baker/model-pick-2026-11-07/CONSENSUS.md).
#
# For an AWS p5en.48xlarge (8 x H200) running "Deep Learning Base OSS Nvidia Driver GPU AMI
# (Ubuntu 24.04)", 2 TB disk, logged in as ubuntu, security group allowing only TCP 8443 from
# your own address:
#
#   [ -d mabillon ] || git clone -q https://github.com/shaque32/mabillon.git
#   git -C mabillon checkout -q <the commit you were given>
#   bash mabillon/deploy/model_server/launch.sh          # starts in the background
#   bash mabillon/deploy/model_server/launch.sh status   # how far it is
#
# Steps: install the pinned engine in a venv; download the pinned weights revision (about
# 770 GB); start the engine on 127.0.0.1 only, one sequence at a time; run the first-boot
# checks (weights manifest, engine version, a synthetic repeat smoke test); then start the
# gateway on port 8443 with TLS and a bearer token. The token and the certificate fingerprint
# are printed once at the end: give them to whoever runs the endpoint checks.
#
# The machine bills about $63/h (unverified). It shuts itself down STOP_AFTER_MIN minutes after
# start (default 240); set STOP_AFTER_MIN=0 to keep it up. Nothing about a case is written to
# disk: the engine's request logging is off and the gateway logs only method, path, status.
set -eEuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PINS="${PINS:-$HERE/pins.json}"
OPT="${OPT:-$HOME/mabillon-server}"
LOG="$HOME/model-server.log"
STOP_AFTER_MIN="${STOP_AFTER_MIN:-240}"
ENGINE_PORT=8001
export PIP_DISABLE_PIP_VERSION_CHECK=1

if [ "${1:-}" = "status" ]; then
  tail -n 8 "$LOG" 2> /dev/null || echo "(no log yet at $LOG)"
  [ -f "$OPT/state.json" ] && cat "$OPT/state.json"
  exit 0
fi
if [ -z "${MABILLON_SERVER_CHILD:-}" ]; then
  MABILLON_SERVER_CHILD=1 nohup setsid bash "${BASH_SOURCE[0]}" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "Started; the download alone takes a while. Check with: bash ${BASH_SOURCE[0]} status"
  exit 0
fi

say() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
die() { say "STOPPED: $*"; exit 1; }
trap 'die "line $LINENO failed"' ERR
# pin model repo -> the value at pins.json["model"]["repo"]
pin() {
  python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
for k in sys.argv[2:]:
    d = d[k]
print(d)' "$PINS" "$@"
}

mkdir -p "$OPT"
if [ "$STOP_AFTER_MIN" != "0" ]; then
  sudo shutdown -h "+$STOP_AFTER_MIN" || say "could not schedule the shutdown; stop the machine yourself"
fi

REPO_ID="$(pin model repo)"
REV="$(pin model revision)"
SERVED="$(pin model served_name)"
ENGINE_VERSION="$(pin engine version)"
TP="$(pin serve tensor_parallel_size)"
MAXLEN="$(pin serve max_model_len)"
SEED="$(pin serve seed)"
EXTRA="$(python3 -c "import json; print(' '.join(json.load(open('$PINS'))['serve']['extra_args']))")"
eval "$(python3 -c "import json,shlex; [print(f'export {k}={shlex.quote(v)}') for k,v in json.load(open('$PINS'))['serve']['env'].items()]")"

say "1/5 engine: vllm==$ENGINE_VERSION"
[ -x "$OPT/venv/bin/python" ] || python3 -m venv "$OPT/venv"
"$OPT/venv/bin/pip" install -q "vllm==$ENGINE_VERSION" "huggingface_hub[cli]"

say "2/5 weights: $REPO_ID@$REV"
"$OPT/venv/bin/hf" download "$REPO_ID" --revision "$REV" --local-dir "$OPT/weights" > /dev/null

say "3/5 engine on 127.0.0.1:$ENGINE_PORT, one sequence at a time"
# shellcheck disable=SC2086 # EXTRA is a list of flags from pins.json
"$OPT/venv/bin/vllm" serve "$OPT/weights" --served-model-name "$SERVED" \
  --host 127.0.0.1 --port "$ENGINE_PORT" --tensor-parallel-size "$TP" \
  --max-model-len "$MAXLEN" --max-num-seqs 1 --seed "$SEED" \
  --disable-log-requests --disable-uvicorn-access-log $EXTRA > "$OPT/engine.log" 2>&1 &
for _ in $(seq 1 180); do
  curl -sf "http://127.0.0.1:$ENGINE_PORT/health" > /dev/null && break
  sleep 10
done
curl -sf "http://127.0.0.1:$ENGINE_PORT/health" > /dev/null || die "engine did not start; see $OPT/engine.log"

say "4/5 first-boot checks (manifest, engine version, synthetic repeat)"
"$OPT/venv/bin/python" "$HERE/firstboot.py" --pins "$PINS" --weights "$OPT/weights" \
  --state "$OPT/state.json" --upstream "http://127.0.0.1:$ENGINE_PORT" \
  || die "first-boot checks failed; the gateway stays closed (see $OPT/state.json)"

say "5/5 gateway on :8443 (TLS, bearer token)"
if [ ! -f "$OPT/tokens" ]; then
  umask 077
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$OPT/tokens"
fi
if [ ! -f "$OPT/cert.pem" ]; then
  openssl req -x509 -newkey rsa:3072 -nodes -days 30 -subj "/CN=mabillon-model-server" \
    -keyout "$OPT/key.pem" -out "$OPT/cert.pem" 2> /dev/null
fi
"$OPT/venv/bin/python" "$HERE/gateway.py" --pins "$PINS" --state "$OPT/state.json" \
  --tokens "$OPT/tokens" --upstream "http://127.0.0.1:$ENGINE_PORT" --port 8443 \
  --cert "$OPT/cert.pem" --key "$OPT/key.pem" >> "$OPT/gateway.log" 2>&1 &
say "READY. Token file: $OPT/tokens (read it with: cat $OPT/tokens)"
say "Certificate SHA-256: $(openssl x509 -in "$OPT/cert.pem" -noout -fingerprint -sha256 | cut -d= -f2)"
say "Weights manifest: $(python3 -c "import json; print(json.load(open('$OPT/state.json'))['manifest_sha256'])")"
wait
