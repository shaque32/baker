"""First-boot checks for the Mabillon model server. The gateway refuses every request until
they pass and write state.json.

1. manifest: SHA-256 of every weights file at the pinned revision, written to manifest.json; its
   own SHA-256 is the weights fingerprint /health reports. When pins.json carries an expected
   manifest hash (after the first audited boot), a different one fails closed.
2. engine: the installed engine version must equal the pin.
3. repeat: one synthetic prompt (no case data), sent twice to the engine on 127.0.0.1 with the
   pinned settings, must come back byte-identical. This is a smoke test only; the real repeat
   check is eval/probe's full run through the gateway (plans/secure-cloud-container.md).

Usage (launch.sh runs it):
  python firstboot.py --pins pins.json --weights /opt/mabillon/weights --state state.json \
      --upstream http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Synthetic, fixed, and shaped like a stance call: no case data ever goes through this check.
SMOKE_PROMPT = (
    "Label the stance of the record toward the assumption. Answer as JSON with keys stance"
    " (supports, contradicts, complicates or irrelevant), quote and rationale.\n"
    "Assumption: the phone was in Boston at 10:02.\n"
    'Record: GPS fix 42.36,-71.06 "Boston" at 10:02.'
)


def file_sha256(path: Path, chunk: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def manifest(weights: Path) -> dict[str, str]:
    """Relative path -> SHA-256 for every file under the weights folder (cache folders left
    out), in sorted order."""
    out = {}
    for p in sorted(weights.rglob("*")):
        if p.is_file() and ".cache" not in p.relative_to(weights).parts:
            out[p.relative_to(weights).as_posix()] = file_sha256(p)
    if not out:
        raise SystemExit(f"{weights}: no files")
    return out


def manifest_sha256(files: dict[str, str]) -> str:
    text = "".join(f"{sha}  {name}\n" for name, sha in sorted(files.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def engine_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001 - not installed reads as no version
        return None


def gpu_name() -> str | None:
    try:
        out = subprocess.run(  # noqa: S603
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],  # noqa: S607
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout.strip().splitlines()  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{len(out)} x {out[0]}" if out else None


def smoke_body(pins: dict[str, Any]) -> dict[str, Any]:
    serve = pins["serve"]
    return {
        "model": pins["model"]["served_name"],
        "messages": [{"role": "user", "content": SMOKE_PROMPT}],
        "temperature": 0,
        "seed": serve["seed"],
        "max_tokens": min(2048, int(serve["max_tokens"])),
        "n": 1,
        "stream": False,
    }


def post_upstream(upstream: str, body: dict[str, Any]) -> bytes:
    if not upstream.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit(f"upstream {upstream!r}: the engine must be on 127.0.0.1")
    req = urllib.request.Request(  # noqa: S310 - checked to be 127.0.0.1 above
        upstream.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:  # noqa: S310 - local engine
        return resp.read()


def answer_text(raw: bytes) -> str:
    return json.loads(raw)["choices"][0]["message"]["content"] or ""


def smoke(pins: dict[str, Any], send: Callable[[dict[str, Any]], bytes]) -> dict[str, Any]:
    first, second = answer_text(send(smoke_body(pins))), answer_text(send(smoke_body(pins)))
    return {
        "smoke_identical": first == second,
        "smoke_sha256": [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in (first, second)],
    }


def run(
    pins: dict[str, Any],
    weights: Path,
    send: Callable[[dict[str, Any]], bytes],
    version_of: Callable[[str], str | None] = engine_version,
    gpu: Callable[[], str | None] = gpu_name,
) -> dict[str, Any]:
    files = manifest(weights)
    fingerprint = manifest_sha256(files)
    expected = pins["model"].get("manifest_sha256")
    state: dict[str, Any] = {
        "revision": pins["model"]["revision"],
        "manifest_sha256": fingerprint,
        "manifest_files": len(files),
        "engine_version": version_of(pins["engine"]["package"]),
        "gpu": gpu(),
    }
    if expected and expected != fingerprint:
        state["manifest_sha256"] = None
        state["problem"] = f"weights manifest {fingerprint} is not the pinned {expected}"
        return state
    state.update(smoke(pins, send))
    state["files"] = files
    return state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pins", type=Path, required=True)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--state", type=Path, required=True)
    ap.add_argument("--upstream", default="http://127.0.0.1:8001")
    args = ap.parse_args(argv)
    pins = json.loads(args.pins.read_text(encoding="utf-8"))
    state = run(pins, args.weights, lambda body: post_upstream(args.upstream, body))
    files = state.pop("files", None)
    if files is not None:
        (args.state.parent / "manifest.json").write_text(
            json.dumps(files, indent=1) + "\n", encoding="utf-8"
        )
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))
    ok = (
        state.get("manifest_sha256")
        and state.get("smoke_identical")
        and (state.get("engine_version") == pins["engine"]["version"])
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
