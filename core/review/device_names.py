"""The names a government document uses for a phone, as the expert recorded them.

An affidavit calls a phone "TARGET PHONE" or "Item 1"; the extraction calls it "Apple D201AP".
Nothing in the data ties the two, so the expert says which device each name means, with
core/review/actions.name_device. The audit log is the record: each `device.names` entry gives
one device's whole list of names, and the newest entry for a device is its list (an empty list
clears it). The assumption filler matches a phone a claim names against these names as well as
the device's id, source id and label, and the report lists each name as an expert statement.
"""

from __future__ import annotations

import json
import re
import sqlite3

ACTION = "device.names"


def name_key(name: str) -> str:
    """How a phone name is compared: case and spacing do not count (as the filler compares)."""
    return re.sub(r"\s+", "", name.casefold())


def named_by(conn: sqlite3.Connection) -> list[tuple[str, str, str, str, list[str]]]:
    """(device id, device label, actor, at_utc, names) for each device's newest entry that
    gives it names, in device order, for the report."""
    newest: dict[str, tuple[str, str, list[str]]] = {}
    for actor, at, payload in conn.execute(
        "SELECT actor, at_utc, payload_json FROM audit_log WHERE action = ? ORDER BY seq",
        (ACTION,),
    ):
        p = json.loads(payload)
        newest[str(p["device_id"])] = (actor, at, [str(n) for n in p.get("names") or []])
    labels = dict(conn.execute("SELECT id, label FROM devices"))
    return [
        (did, labels.get(did, did), actor, at, names)
        for did, (actor, at, names) in sorted(newest.items())
        if names
    ]


def logged_names(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Device id -> the names the expert's newest `device.names` entry gives it."""
    return {did: names for did, _label, _actor, _at, names in named_by(conn)}
