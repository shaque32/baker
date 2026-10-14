"""Convert thread 3's probe set (eval/probe_draft/*.jsonl) into the runner's item files.

Usage: python -m eval.probe.from_draft <probe_draft.jsonl> [--out eval/out/probe_items]

Reads the JSON lines directly, so it works before that branch merges. Items are converted
as they are; nothing is edited to help a model pass.

An item in Baker's own wording (eval/stancedata, one that names its record's phone) reads as
Baker shows a case's records: each sender as core.audit.readable prints it, without the
internal account id, a chat record's context opening with its members line, and the claim
carried for a stance prompt that has a {claim} slot (eval/probe/run_probe.py).

Any other item (the signed probe set, P001 to P088) is shown in the product's layout
(layout="product", the default since 2026-10-14): the RECORD is the message text alone, as
core/audit/stance.default_record sends it, and the context is laid out as
core/audit/context.render_context lays it out, with its header line ("Times are the phone's local
time"), '>>' on the record under review and each message's direction. layout="product_members"
also opens the context with the chat's members line (core/audit/readable.members_line), built
from the senders the excerpt shows, as stance prompt v1.1's wiring will send it. The earlier
layout (layout="legacy") put the "[time] sender (account id):" header inside the RECORD,
so a model that quoted it had its answer discarded by the quote check, and it showed no
direction, no members and no note that times are local; the grading audit of 2026-10-14
(cloud-bench/2026-10-14/GRADING_AUDIT.md) found those gaps decided items. Labels are untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.audit.context import HEADER
from core.audit.readable import members_line

# "product": core/audit/context.py's layout as the product sends it today. "product_members":
# the same, opened by the chat's members line, as signed stance prompt v1.1 and its pipeline
# wiring will send it (PROPOSED_CHANGES.md, part three). "legacy": the probe before 2026-10-14.
LAYOUTS = ("product", "product_members", "legacy")
# The product's context header. The signed probe set prints the phone's own account "(owner)",
# as stance prompt v1.1 and core/audit/readable.py do, where context.py still says
# "(this phone)"; the sentence is changed to match the lines it describes.
PROBE_HEADER = HEADER.replace("'(this phone)'", "'(owner)'")


def fmt(line: dict[str, Any], baker: bool = False) -> str:
    """One context line. A Baker-form sender already prints its app and identifier; its
    account_id is Baker's internal id, which the product never shows a model."""
    if baker:
        return f"[{line['local_time']}] {line['sender']}: {line['text']}"
    return f"[{line['local_time']}] {line['sender']} ({line['account_id']}): {line['text']}"


def product_line(line: dict[str, Any], is_target: bool) -> str:
    """One context line as core/audit/context.render_context prints it. The internal account
    id is left out, as the product shows only the app and account; the direction follows the
    "(owner)" mark, the phone's own account."""
    mark = ">>" if is_target else "  "
    direction = "outgoing" if "(owner)" in line["sender"] else "incoming"
    body = line["text"].replace("\r\n", "\n").replace("\r", "\n").replace("\n", " \\n ")
    return f"{mark} [{line['local_time']}] {line['sender']}, {direction}: {body}"


def member(sender: str) -> str:
    """A sender as the members line prints it: app and account, "(owner)" for the phone's own
    account, and no name the phone saved ("SMS +12125550122 Marc Garage" -> "SMS
    +12125550122"), so an account seen under two handles is one member."""
    parts = sender.split()
    if len(parts) < 2:
        return sender
    return f"{parts[0]} {parts[1]}" + (" (owner)" if "(owner)" in sender else "")


def product_context(item: dict[str, Any], members: bool = False) -> str:
    lines = list(item["context"])
    lines.insert(item["target_index"], item["target"])
    shown = [product_line(x, i == item["target_index"]) for i, x in enumerate(lines)]
    head = [members_line(member(x["sender"]) for x in lines)] if members else []
    return "\n".join([*head, PROBE_HEADER, *shown])


def convert(item: dict[str, Any], layout: str = "product") -> tuple[dict[str, Any], dict[str, Any]]:
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {LAYOUTS}, not {layout!r}")
    baker = bool(item.get("device_id"))
    product = layout != "legacy" and not baker
    lines = list(item["context"])
    lines.insert(item["target_index"], item["target"])
    shown = [fmt(x, baker) for x in lines]
    if item.get("baker_members"):
        shown.insert(0, members_line(item["baker_members"]))
    context = product_context(item, layout == "product_members") if product else "\n".join(shown)
    common = {"id": item["probe_id"], "category": item["category"], "trap": item.get("trap"),
              "lang": item["lang"], "assumption": item["assumption"],
              "context": context, "disputed": item.get("disputed"),
              "labeled_by": item.get("labeled_by")}  # fmt: skip
    reviewer = {**common, "overreach": item["category"] == "overreach",
                "quote": item["proposed_quote"], "expected": item["gold_review"]}  # fmt: skip
    record = item["target"]["text"] if product else fmt(item["target"], baker)
    stance = {**common, "record_text": item["target"]["text"], "record": record,
              "kind": item.get("assumption_kind"), "expected": item["gold_stance"]}  # fmt: skip
    if item.get("baker_claim"):
        stance["claim"] = item["baker_claim"]
    return reviewer, stance


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("draft", type=Path)
    ap.add_argument("--out", type=Path, default=Path("eval/out/probe_items"))
    args = ap.parse_args(argv)
    rows = [json.loads(x) for x in args.draft.read_text(encoding="utf-8").splitlines() if x.strip()]
    args.out.mkdir(parents=True, exist_ok=True)
    with (
        (args.out / "reviewer.jsonl").open("w", encoding="utf-8", newline="\n") as rf,
        (args.out / "stance.jsonl").open("w", encoding="utf-8", newline="\n") as sf,
    ):
        for row in rows:
            r, s = convert(row)
            rf.write(json.dumps(r, ensure_ascii=False) + "\n")
            sf.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{len(rows)} items -> {args.out}/reviewer.jsonl, stance.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
