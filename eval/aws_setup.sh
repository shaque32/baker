# Shared setup for Mabillon's runs on a rented AWS NVIDIA machine. Sourced, not run, by
# eval/validation/aws_run.sh and eval/probe/aws_repeat.sh, which set REPO, WORK, PY and PINS and
# define say and die first.
#
# For a g5.xlarge (A10G) or g6.xlarge (L4) on "Deep Learning Base OSS Nvidia Driver GPU AMI
# (Ubuntu 24.04)". Everything it fetches is public and checked by SHA-256 from
# packaging/windows/pins.json: the llama-cpp-python source and the model file.

pin() { python3 -c 'import json, sys; d = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d = d[k]
print(d)' "$PINS" "$1"; }

# Python 3.12 in $WORK/venv and Mabillon from $REPO, with the synthetic-data extra.
aws_install() {
  if [ ! -x "$PY" ]; then
    command -v uv > /dev/null || [ -x "$HOME/.local/bin/uv" ] || curl -LsSf https://astral.sh/uv/install.sh | sh
    "$HOME/.local/bin/uv" venv -q --seed --python 3.12 "$WORK/venv" 2> /dev/null \
      || uv venv -q --seed --python 3.12 "$WORK/venv"
  fi
  "$PY" -m pip install -q -e "$REPO[synthetic]"
}

# The pinned llama-cpp-python, built from its pinned source for the graphics card. $1 is the
# step label for the log ("3/6").
aws_build_runtime() {
  local llama_version sdist
  llama_version=$(pin llama_cpp_python.version)
  if "$PY" -c 'import sys, llama_cpp
sys.exit(0 if llama_cpp.__version__ == sys.argv[1] and llama_cpp.llama_supports_gpu_offload() else 1)' \
    "$llama_version" 2> /dev/null; then
    say "$1 model runtime already built"
    return 0
  fi
  say "$1 building the model runtime for the graphics card (about 15 minutes)"
  mkdir -p "$WORK/sdist"
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
}

# The pinned model file in $WORK/models, checked by SHA-256; sets MODEL to its path, writes the
# product's model settings ($WORK/model.json, exported as MABILLON_MODEL_CONFIG) and runs the
# model check. $1 is the step label for the log.
aws_get_model() {
  MODEL="$WORK/models/$(pin model.file)"
  mkdir -p "$WORK/models"
  if [ ! -f "$MODEL" ]; then
    say "$1 downloading the AI model (9 GB)"
    curl -fL --retry 5 -C - -s -o "$MODEL.part" "$(pin model.url)"
    echo "$(pin model.sha256)  $MODEL.part" | sha256sum -c --quiet || {
      rm -f "$MODEL.part"
      die "the model download is damaged; run the start command again"
    }
    mv "$MODEL.part" "$MODEL"
  else
    say "$1 AI model already downloaded"
  fi
  export MABILLON_MODEL_CONFIG="$WORK/model.json"
  "$PY" -c 'import json, sys
json.dump({"name": sys.argv[1], "path": sys.argv[2], "sha256": sys.argv[3], "n_ctx": int(sys.argv[4])},
          open(sys.argv[5], "w"), indent=2)' \
    "$(pin model.name)" "$MODEL" "$(pin model.sha256)" "$(pin model.n_ctx)" "$MABILLON_MODEL_CONFIG"
  "$WORK/venv/bin/mabillon" model-check || die "the model check failed"
}

# What the machine is, as JSON in $1: the AWS image and instance type (from the instance's own
# metadata service, which never leaves the machine) and the CUDA compiler on it. The graphics card
# and its driver are recorded by the Python side (nvidia-smi). A value it cannot read is null.
aws_host_json() {
  local token ami itype nvcc
  token=$(curl -s -m 2 --noproxy "*" -f -X PUT http://169.254.169.254/latest/api/token \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2> /dev/null || true)
  ami=$(curl -s -m 2 --noproxy "*" -f -H "X-aws-ec2-metadata-token: $token" \
    http://169.254.169.254/latest/meta-data/ami-id 2> /dev/null || true)
  itype=$(curl -s -m 2 --noproxy "*" -f -H "X-aws-ec2-metadata-token: $token" \
    http://169.254.169.254/latest/meta-data/instance-type 2> /dev/null || true)
  nvcc=${CUDACXX:-/usr/local/cuda/bin/nvcc}
  [ -x "$nvcc" ] || nvcc=$(ls /usr/local/cuda-*/bin/nvcc 2> /dev/null | sort -V | tail -n 1 || true)
  nvcc=$("${nvcc:-nvcc}" --version 2> /dev/null | grep -o 'release [0-9.]*, V[0-9.]*' || true)
  python3 -c 'import json, sys
keys = ("aws_ami_id", "aws_instance_type", "cuda_compiler")
json.dump({k: (v or None) for k, v in zip(keys, sys.argv[2:])}, open(sys.argv[1], "w"), indent=2)' \
    "$1" "$ami" "$itype" "$nvcc"
}
