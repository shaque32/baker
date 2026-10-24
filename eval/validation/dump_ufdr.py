"""Independent dump of a Cellebrite report.xml (ElementTree only, never Mabillon's importer).

The validation keys cite records by this dump's source_index (eval/validation/PREREGISTERED.md);
it made the iOS 15 dump in project files, and the scorer's test runs it on synthetic packages.
It imports nothing from core/ on purpose.

Usage: python3 -I -m eval.validation.dump_ufdr <report.xml> <out_dir>
Writes messages.jsonl (chat and standalone instant messages, SMS), calls.jsonl, contacts.jsonl.
Every row keeps the model id and source_index so a key can cite the record.
Copies under RelatedModels are kept with related=True; readers use the holder.
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://pa.cellebrite.com/report/2.0}"
TOP = {"Chat", "InstantMessage", "Call", "Contact"}


def t(el):
    return el.tag.removeprefix(NS)


def field(m, name):
    for c in m:
        if t(c) == "field" and c.get("name") == name:
            v = c.find(NS + "value")
            if v is None:
                return None
            return (v.get("formattedTimestamp") and v.text) or v.text
    return None


def party(p):
    return {
        "id": field(p, "Identifier"),
        "name": field(p, "Name"),
        "owner": field(p, "IsPhoneOwner") == "True",
    }


def parties(m, name):
    out = []
    for c in m:
        if t(c) in ("multiModelField", "modelField") and c.get("name") == name:
            out += [party(p) for p in c.findall(NS + "model")]
    return out


def message(m, chat=None, related=False):
    atts = []
    for c in m:
        if t(c) == "multiModelField" and c.get("name") == "Attachments":
            atts = [field(a, "Filename") for a in c.findall(NS + "model")]
    frm = parties(m, "From")
    return {
        "kind": "message",
        "id": m.get("id"),
        "source_index": m.get("source_index"),
        "deleted_state": m.get("deleted_state"),
        "related": related,
        "app": field(m, "Source"),
        "chat_id": chat.get("id") if chat is not None else None,
        "time_utc": field(m, "TimeStamp"),
        "from": frm[0] if frm else None,
        "to": parties(m, "To"),
        "body": field(m, "Body"),
        "attachments": atts,
        "type": field(m, "Type"),
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    src, out = Path(argv[0]), Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    files = {
        k: open(out / f"{k}.jsonl", "w", encoding="utf-8")
        for k in ("messages", "calls", "contacts", "chats")
    }
    depth = 0
    # Public test packages only; Python's expat resolves no external entities.
    for ev, el in ET.iterparse(src, events=("start", "end")):  # noqa: S314
        if ev == "start":
            if t(el) == "model":
                depth += 1
            continue
        if t(el) != "model":
            continue
        depth -= 1
        if depth != 0:
            continue
        kind = el.get("type")
        if kind == "Chat":
            ps = parties(el, "Participants")
            files["chats"].write(
                json.dumps(
                    {
                        "id": el.get("id"),
                        "app": field(el, "Source"),
                        "participants": ps,
                        "deleted_state": el.get("deleted_state"),
                    }
                )
                + "\n"
            )
            for c in el:
                if t(c) == "multiModelField" and c.get("name") == "Messages":
                    for m in c.findall(NS + "model"):
                        row = message(m, el)
                        row["participants"] = ps
                        files["messages"].write(json.dumps(row, ensure_ascii=False) + "\n")
        elif kind == "InstantMessage":
            files["messages"].write(json.dumps(message(el), ensure_ascii=False) + "\n")
        elif kind == "Call":
            ps = parties(el, "Parties")
            files["calls"].write(
                json.dumps(
                    {
                        "kind": "call",
                        "id": el.get("id"),
                        "source_index": el.get("source_index"),
                        "deleted_state": el.get("deleted_state"),
                        "app": field(el, "Source"),
                        "time_utc": field(el, "TimeStamp"),
                        "direction": field(el, "Direction"),
                        "status": field(el, "Status"),
                        "type": field(el, "Type"),
                        "duration": field(el, "Duration"),
                        "parties": ps,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        elif kind == "Contact":
            entries = []
            for c in el:
                if t(c) == "multiModelField" and c.get("name") == "Entries":
                    entries = [
                        {"category": field(e, "Category"), "value": field(e, "Value")}
                        for e in c.findall(NS + "model")
                    ]
            files["contacts"].write(
                json.dumps(
                    {
                        "kind": "contact",
                        "id": el.get("id"),
                        "source_index": el.get("source_index"),
                        "app": field(el, "Source"),
                        "name": field(el, "Name"),
                        "entries": entries,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        el.clear()
    for f in files.values():
        f.close()


if __name__ == "__main__":
    main()
