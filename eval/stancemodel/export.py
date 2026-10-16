"""Write a trained checkpoint as one self-contained model folder (float16 weights, tokenizer,
metadata with the model file's SHA-256 and the decision policy).

    python -m eval.stancemodel.export --base <local mdeberta-v3-base dir> \
        --run eval/out/stancemodel/<run> --weights last --out eval/out/stancemodel/<run>/model \
        [--policy <policy.json>]

--weights is "last" (the end of training) or "epochN" (the end of epoch N). Local files only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

from eval.stancemodel import features
from eval.stancemodel.model import export, new_model
from eval.stancemodel.policy import Policy
from eval.stancemodel.train import BASE_MODEL, BASE_REVISION


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--weights", default="last", help='"last" or "epochN"')
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--policy", type=Path, default=None, help="tuned on the dev split only")
    args = ap.parse_args(argv)

    from transformers import AutoTokenizer

    config = json.loads((args.run / "config.json").read_text(encoding="utf-8"))
    if args.weights == "last":
        state = torch.load(args.run / "last.pt", map_location="cpu", weights_only=False)
        weights, step = state["model"], state["step"]
        if step != config["total_steps"]:
            raise SystemExit(f"training stopped at step {step} of {config['total_steps']}")
    else:
        weights = torch.load(args.run / f"{args.weights}.pt", map_location="cpu")
        step = int(args.weights.removeprefix("epoch")) * (config["total_steps"] // config["epochs"])
    model = new_model(args.base, dropout=config["dropout"])
    missing, unexpected = model.load_state_dict(weights, strict=False)
    trained = {n for n, p in model.named_parameters() if p.requires_grad}
    if unexpected or trained & set(missing):
        raise SystemExit(f"checkpoint does not fit: missing {missing}, unexpected {unexpected}")
    policy = Policy.from_dict(
        json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else None
    )
    tok = AutoTokenizer.from_pretrained(args.base, local_files_only=True)
    meta = {
        "arm": "classifier",
        "base_model": BASE_MODEL,
        "base_revision": BASE_REVISION,
        "train_sha256": config["train_sha256"],
        "features_version": features.VERSION,
        "max_len": config["max_len"],
        "dropout": config["dropout"],
        "weights": args.weights,
        "step": step,
        "policy": policy.to_dict(),
        "training": config,
    }
    digest = export(model, tok, args.out, meta)
    print(f"wrote {args.out} (model sha256 {digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
