"""Training items for Baker's stance model. Every name, number and chat is invented.

    python -m eval.train.generate --n 12000 --seed 1 --out eval/out/stancedata/train.jsonl

Writes the items (one JSON line each) and `<out>.manifest.json` beside them. Item i is built
from `item_rng(GENERATOR, seed, i)` and the package's fixed pools alone: a scenario's random
stream is seeded by the id of its first item, and its sibling items (same chat and record,
different assumption and family) take the following ids and share a group. The same command
always writes a byte-identical file.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from eval.stancedata.chat import build_item, item_rng, write_jsonl
from eval.stancedata.families import family
from eval.stancedata.model import GenItem
from eval.train.scenes_c import pick_scenario, takes_fact

GENERATOR = "eval.train 1.0.0"
SOURCE = "train_gen"


def generate(n: int, seed: int) -> list[GenItem]:
    """The first n items for this seed, in id order.

    Each scenario's rng is seeded from the generator, the seed and the index of its first item,
    so a shorter run is a prefix of a longer one. The run is cut at exactly n, so the final
    group can be left with fewer siblings than the scenario made; it keeps its Tg id.
    """
    items: list[GenItem] = []
    slot = 0  # fact scenarios built so far; fact_pool spreads the facts evenly over it
    while len(items) < n:
        first = len(items) + 1
        rng = item_rng(GENERATOR, seed, first)
        scenario = pick_scenario(rng)
        chat, specs = scenario(rng, slot)
        slot += takes_fact(scenario)
        group = f"Tg{first:06d}" if len(specs) > 1 else None
        for spec in specs:
            if len(items) >= n:
                break
            items.append(
                build_item(
                    probe_id=f"T{len(items) + 1:06d}",
                    family_id=spec.family,
                    source=SOURCE,
                    generator=GENERATOR,
                    lang=chat.lang,
                    kind=spec.kind,
                    assumption=spec.assumption,
                    msgs=chat.msgs,
                    target=chat.target,
                    quote=spec.quote,
                    rationale=spec.rationale,
                    group=group,
                    tz=chat.tz,
                )
            )
    return items


def manifest(items: list[GenItem], seed: int, sha256: str) -> dict:
    def count(key) -> dict[str, int]:
        return dict(sorted(Counter(key(it) for it in items).items()))

    return {
        "generator": GENERATOR,
        "seed": seed,
        "n": len(items),
        "sha256": sha256,
        "by_family": count(lambda it: it.family),
        "by_stance": count(lambda it: family(it.family).stance.value),
        "by_lang": count(lambda it: it.lang),
        "by_assumption_kind": count(lambda it: it.assumption_kind.value),
        "groups_with_siblings": sum(
            1 for g, k in Counter(it.group for it in items).items() if k > 1
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("eval/out/stancedata/train.jsonl"))
    args = ap.parse_args(argv)
    started = time.perf_counter()
    items = generate(args.n, args.seed)
    sha = write_jsonl(items, args.out)
    m = manifest(items, args.seed, sha)
    side = args.out.with_name(args.out.name + ".manifest.json")
    side.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items to {args.out} (sha256 {sha[:16]}) in "
          f"{time.perf_counter() - started:.1f}s")  # fmt: skip
    print(json.dumps({k: m[k] for k in ("by_stance", "by_lang")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
