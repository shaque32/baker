"""Score the validation-v1 run (eval/validation/PREREGISTERED.md), once, with the code at main.

    python -m eval.validation.score_hickman --results results.zip --keys DIR --dump DIR --out DIR

--keys holds the signed answer keys (gold.jsonl, gold_b2.jsonl, gold_b3.jsonl) and --dump the
independent ElementTree dump of the phone's report.xml (eval/validation/dump_ufdr.py). Both stay
in project files. The run's case.db is copied; the copy is scored and the original never changes.

1. Key evidence: each key record (`ufdr:source_index:N`) is matched to Mabillon's records by
   content, since Mabillon's ids are positional and keep no UFDR id. A message must agree on its
   raw time (the same report.xml text both sides read), its app and its body; a call on its raw
   time, its app and its duration; a contact on its name and one of its identifiers (a phone
   number by its last ten digits). A key with no single match (none, several, or a kind
   Mabillon does not cite, such as a chat) is listed, never matched to a near miss.
2. R1, the run as it stands: the three primary measures, key-evidence recall (counted per key
   record, so a contact Mabillon keeps as one row per identifier still counts once), label counts.
3. R2, the simulated expert (eval/simulated_expert.py) on the mapped keys, then the rules again
   (`mabillon redecide`), scored by eval/validation/card.py.
4. Import counts beside the dump's.
Writes DIR/score.json and DIR/score.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.contracts import GoldClaim, Stance, Verdict
from eval.validation.card import build_card, load_checks, rate, render_markdown
from eval.validation.hickman_run import TYPE_ALIASES

KEY_FILES = ("gold.jsonl", "gold_b2.jsonl", "gold_b3.jsonl")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_keys(keys: Path) -> tuple[list[GoldClaim], dict[str, str]]:
    gold: list[GoldClaim] = []
    hashes: dict[str, str] = {}
    for name in KEY_FILES:
        path = keys / name
        hashes[name] = _sha256(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row["claim_type"] = TYPE_ALIASES.get(row["claim_type"], row["claim_type"])
                gold.append(GoldClaim.model_validate(row))
    return gold, hashes


def load_dump(dump: Path) -> tuple[dict[str, dict], dict[str, str | None], dict[str, int]]:
    """Records by source_index, each chat's app by chat id, and top-level counts."""
    by_index: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for kind in ("messages", "calls", "contacts"):
        rows = [
            json.loads(x) for x in (dump / f"{kind}.jsonl").read_text("utf-8").splitlines() if x
        ]
        counts[kind] = sum(1 for r in rows if not r.get("related"))
        for r in rows:
            by_index[str(r["source_index"])] = r
    chat_lines = (dump / "chats.jsonl").read_text("utf-8").splitlines()
    chats = {c["id"]: c.get("app") for c in map(json.loads, filter(None, chat_lines))}
    # Mabillon makes a thread only for a chat that holds a message, so count those.
    holding = {r.get("chat_id") for r in by_index.values() if r.get("kind") == "message"}
    counts["chats_with_messages"] = sum(1 for c in chats if c in holding)
    return by_index, chats, counts


def _seconds(duration: str | None) -> int | None:
    """A duration in whole seconds the way the importer stores it: plain seconds, or
    [d.]hh:mm:ss with any fraction of a second dropped."""
    t = (duration or "").strip()
    if re.fullmatch(r"\d+", t):
        return int(t)
    m = re.fullmatch(r"(?:(\d+)\.)?(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?", t)
    if not m:
        return None
    d, h, mi, s = m.groups()
    return int(d or 0) * 86400 + int(h) * 3600 + int(mi) * 60 + int(s)


def _ident(value: str) -> str:
    """An identifier as both sides can compare it: a phone number by its last ten digits (the
    importer may write +1 (919) 888-7386 as +19198887386), anything else lowercased."""
    if re.fullmatch(r"[\d\s()+\-.]+", value) and sum(c.isdigit() for c in value) >= 7:
        return "".join(c for c in value if c.isdigit())[-10:]
    return value.strip().lower()


def _app(rec: dict, chats: dict[str, str | None]) -> str:
    """The app Mabillon files a record under: its own Source, else its chat's, else "SMS" for
    a standalone SMS or MMS and "unknown" for anything else."""
    default = "SMS" if rec.get("model") in ("SMS", "MMS") else "unknown"
    return rec.get("app") or chats.get(rec.get("chat_id") or "") or default


def match_record(
    conn: sqlite3.Connection, rec: dict, chats: dict[str, str | None] | None = None
) -> tuple[list[str], str]:
    """Mabillon record ids for one dump record, and why when there is no single match. Every
    field compared must agree; a record that differs in any of them is not a match."""
    kind = rec.get("kind")
    chats = chats or {}
    if kind == "message":
        rows = conn.execute(
            "SELECT m.id FROM messages m JOIN threads t ON t.id = m.thread_id"
            " WHERE m.ts_raw = ? AND t.app = ? AND m.body = ?",
            (rec["time_utc"], _app(rec, chats), rec.get("body") or ""),
        ).fetchall()
        ids = [r[0] for r in rows]
    elif kind == "call":
        rows = conn.execute(
            "SELECT id FROM calls WHERE ts_raw = ? AND app = ? AND duration_s IS ?",
            (rec["time_utc"], _app(rec, chats), _seconds(rec.get("duration"))),
        ).fetchall()
        ids = [r[0] for r in rows]
    elif kind == "contact":
        values = {_ident(e["value"]) for e in rec.get("entries", []) if e.get("value")}
        rows = conn.execute(
            "SELECT id, locator, identifier FROM contacts WHERE name IS ?", (rec.get("name"),)
        ).fetchall()
        hit = {r[1] for r in rows if _ident(r[2]) in values}
        if len(hit) != 1:
            return [], "no contact matches" if not hit else f"{len(hit)} contacts match"
        # Every row Mabillon made from that one contact record (one per identifier).
        return sorted(r[0] for r in rows if r[1] in hit), ""
    else:
        return [], f"kind {kind!r} is not matched"
    if len(ids) == 1:
        return ids, ""
    return [], "no record matches" if not ids else f"{len(ids)} records match"


def map_keys(
    conn: sqlite3.Connection,
    gold: list[GoldClaim],
    dump: dict[str, dict],
    chats: dict[str, str | None],
) -> tuple[list[GoldClaim], dict[str, Any]]:
    """The keys with key_evidence as Mabillon record ids, and every key left unmapped. The
    mapping also keeps, per claim, each mapped key record's ids (a contact has one per
    identifier), so recall counts key records rather than rows."""
    mapped: list[GoldClaim] = []
    unmapped: list[dict[str, str]] = []
    groups: dict[str, dict[str, list[str]]] = {}
    n_keys = 0
    for g in gold:
        ids: list[str] = []
        groups[g.claim_id] = {}
        for key in g.key_evidence:
            n_keys += 1
            index = key.removeprefix("ufdr:source_index:")
            if index in chats:
                why = "a chat, not a record Mabillon cites"
                got: list[str] = []
            elif index not in dump:
                got, why = [], "not in the dump"
            else:
                got, why = match_record(conn, dump[index], chats)
            if got:
                ids.extend(i for i in got if i not in ids)
                groups[g.claim_id][key] = got
            else:
                unmapped.append({"claim_id": g.claim_id, "key": key, "why": why})
        mapped.append(g.model_copy(update={"key_evidence": tuple(ids)}))
    return mapped, {"keys": n_keys, "unmapped": unmapped, "groups": groups}


def _items(conn: sqlite3.Connection, manifest: dict, claim_id: str) -> list:
    from core.pipeline import load_evidence

    return load_evidence(conn, manifest.get(claim_id, {}).get("evidence", []))


def _failed_checks(conn: sqlite3.Connection, manifest: dict, claim_id: str) -> list[str]:
    ids = manifest.get(claim_id, {}).get("checks", [])
    out = []
    for cid in ids:
        row = conn.execute("SELECT outcome FROM check_results WHERE id = ?", (cid,)).fetchone()
        if row and row[0] == "fail":
            out.append(cid)
    return out


def _retrieved(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Records the run sent to the stance labeler, by claim (assumption ids carry the claim)."""
    out: dict[str, set[str]] = {}
    rows = conn.execute(
        "SELECT c.subject_json FROM model_calls c JOIN model_runs r ON r.id = c.model_run_id"
        " WHERE r.purpose = 'stance'"
    )
    for (subject,) in rows:
        ids = json.loads(subject)
        if len(ids) >= 2 and ids[0].startswith("asm:"):
            out.setdefault(ids[0].split(":")[1], set()).add(ids[1])
    return out


def key_recall(
    conn: sqlite3.Connection, run: dict, groups: dict[str, dict[str, list[str]]]
) -> dict[str, Any]:
    """Key-evidence recall as eval/simulated_expert.readiness defines it, counted per mapped key
    record: retrieved when the run sent any of its rows to the stance labeler for the claim,
    surfaced when any of them became a labeled, not irrelevant evidence item."""
    retrieved = _retrieved(conn)
    per_claim: dict[str, dict[str, Any]] = {}
    n_key = n_retrieved = n_surfaced = 0
    all_retrieved: list[str] = []
    any_surfaced: list[str] = []
    for claim_id in sorted(groups):
        keys = groups[claim_id]
        sent = retrieved.get(claim_id, set())
        items = _items(conn, run["manifest"], claim_id)
        shown_ids = {e.record_id for e in items if e.stance is not Stance.IRRELEVANT}
        got = sorted(k for k, ids in keys.items() if sent & set(ids))
        shown = sorted(k for k, ids in keys.items() if shown_ids & set(ids))
        n_key += len(keys)
        n_retrieved += len(got)
        n_surfaced += len(shown)
        if keys and len(got) == len(keys):
            all_retrieved.append(claim_id)
        if shown:
            any_surfaced.append(claim_id)
        per_claim[claim_id] = {
            "key": len(keys),
            "retrieved": len(got),
            "surfaced": len(shown),
            "missed": sorted(set(keys) - set(got)),
        }
    return {
        "key_evidence": n_key,
        "key_evidence_recall_retrieved": rate(n_retrieved, n_key),
        "key_evidence_recall_surfaced": rate(n_surfaced, n_key),
        "claims_all_key_retrieved": all_retrieved,
        "claims_ready_for_expert": any_surfaced,
        "per_claim": per_claim,
    }


def r1_measures(conn: sqlite3.Connection, run: dict, gold: list[GoldClaim]) -> dict[str, Any]:
    from core.pipeline import load_verdict

    manifest = run["manifest"]
    per_claim: dict[str, dict[str, Any]] = {}
    for g in gold:
        v = load_verdict(conn, g.claim_id, run["run_id"])
        items = [e for e in _items(conn, manifest, g.claim_id) if e.stance is not Stance.IRRELEVANT]
        key = set(g.key_evidence)
        per_claim[g.claim_id] = {
            "type": g.claim_type.value,
            "gold": g.gold_verdict.value,
            "r1": v.verdict.value if v else None,
            "failed_checks": _failed_checks(conn, manifest, g.claim_id),
            "supports": sum(e.stance is Stance.SUPPORTS for e in items),
            "contradicts": sum(e.stance is Stance.CONTRADICTS for e in items),
            "contradicts_on_key": sum(
                e.stance is Stance.CONTRADICTS and e.record_id in key for e in items
            ),
        }

    def measure(name: str, base, hit) -> dict[str, Any]:  # noqa: ANN001
        rows = {c: r for c, r in per_claim.items() if base(r)}
        hits = sorted(c for c, r in rows.items() if hit(r))
        by_type: dict[str, dict[str, Any]] = {}
        for t in sorted({r["type"] for r in rows.values()}):
            of_t = [c for c, r in rows.items() if r["type"] == t]
            by_type[t] = rate(sum(c in hits for c in of_t), len(of_t))
        return {"measure": name, **rate(len(hits), len(rows)), "claims": hits, "by_type": by_type}

    contra = Verdict.CONTRADICTED.value
    return {
        "contradicted_without_expert": measure(
            "R1 contradicted, gold not contradicted",
            lambda r: r["gold"] != contra,
            lambda r: r["r1"] == contra,
        ),
        "false_claim_shown_only_as_support": measure(
            "gold contradicted; supports items, no contradicts item, no failed check",
            lambda r: r["gold"] == contra,
            lambda r: r["supports"] > 0 and r["contradicts"] == 0 and not r["failed_checks"],
        ),
        "contradiction_surfaced": measure(
            "gold contradicted; a failed check or a contradicts item on a key record",
            lambda r: r["gold"] == contra,
            lambda r: bool(r["failed_checks"]) or r["contradicts_on_key"] > 0,
        ),
        "no_r1_verdict": sorted(c for c, r in per_claim.items() if r["r1"] is None),
        "per_claim": per_claim,
    }


def label_counts(conn: sqlite3.Connection, run: dict, gold: list[GoldClaim]) -> dict[str, Any]:
    """Stance labels by kind, and how many contradicts labels sit on a gold-contradicted claim's
    key record (beside the measures, never changing them)."""
    stances: Counter[str] = Counter()
    contra_total = contra_on_key = 0
    for g in gold:
        key = set(g.key_evidence) if g.gold_verdict is Verdict.CONTRADICTED else set()
        for e in _items(conn, run["manifest"], g.claim_id):
            stances[e.stance.value] += 1
            if e.stance is Stance.CONTRADICTS:
                contra_total += 1
                contra_on_key += e.record_id in key
    return {
        "labels": dict(sorted(stances.items())),
        "contradicts_on_gold_contradicted_key": rate(contra_on_key, contra_total),
    }


def import_counts(conn: sqlite3.Connection, dump_counts: dict[str, int]) -> dict[str, Any]:
    """Like for like: a thread whose first message came from a source chat stands for that
    chat (standalone messages make threads of their own, which are not counted here)."""
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    ours = {
        "messages": one("SELECT COUNT(*) FROM messages"),
        "calls": one("SELECT COUNT(*) FROM calls"),
        "contacts": one("SELECT COUNT(DISTINCT locator) FROM contacts"),
        "chats_with_messages": one("SELECT COUNT(*) FROM threads WHERE locator LIKE 'Chat[%'"),
    }
    return {k: {"mabillon": ours[k], "dump": dump_counts.get(k)} for k in ours}


def r2(db: Path, run: dict, mapped: list[GoldClaim]) -> dict[str, Any]:
    """The simulated expert on the mapped keys, then the rules again, scored by the card."""
    from core import pipeline
    from core.db import connect
    from core.review.redecide import redecide
    from eval.simulated_expert import SIM_EXPERT, GoldKey, review

    conn = connect(db)
    now = datetime.now(UTC)  # after the audit, so the rules' new run is the latest one
    decided = review(conn, GoldKey(mapped), run["manifest"], lambda: now)
    again = redecide(conn, SIM_EXPERT, lambda: now)
    latest = pipeline.last_run(conn)
    if latest is None or latest["run_id"] != again.run_id:
        raise SystemExit(f"score: the rules' run {again.run_id} is not the latest completed run")
    preds = pipeline.predictions(conn)
    from eval.validation.card import _verdicts

    verdicts = _verdicts(conn, again.run_id)
    conn.close()
    card = build_card(mapped, preds, verdicts, load_checks(db, [g.claim_id for g in mapped]))
    return {"run_id": again.run_id, "simulated_expert": decided.summary(), "card": card}


def score(results: Path, keys: Path, dump: Path, out: Path) -> dict[str, Any]:
    from core import pipeline
    from core.db import connect

    out.mkdir(parents=True, exist_ok=True)
    db = out / "scored.db"
    run_record: dict[str, Any] | None = None  # the run's own run.json: versions, machine, times
    if results.suffix == ".zip":
        with zipfile.ZipFile(results) as z:
            with z.open("case.db") as src, db.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if "run.json" in z.namelist():
                run_record = json.loads(z.read("run.json"))
    else:
        shutil.copyfile(results, db)
    gold, key_hashes = load_keys(keys)
    by_index, chats, dump_counts = load_dump(dump)

    conn = connect(db)
    run = pipeline.last_run(conn)
    if run is None:
        raise SystemExit(f"{results}: no completed audit in case.db")
    mapped, mapping = map_keys(conn, gold, by_index, chats)
    r1 = r1_measures(conn, run, mapped)
    ready = key_recall(conn, run, mapping["groups"])
    labels = label_counts(conn, run, mapped)
    counts = import_counts(conn, dump_counts)
    conn.close()

    result = {
        "results_sha256": _sha256(results),
        "keys_sha256": key_hashes,
        "audit_run": run["run_id"],
        "run_record": run_record,
        "rule_version": run["rule_version"],
        "key_mapping": mapping,
        "r1": r1,
        "key_evidence": ready,
        "labels": labels,
        "import_counts": counts,
        "r2": r2(db, run, mapped),
    }
    (out / "score.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out / "score.md").write_text(render(result), encoding="utf-8")
    return result


def _line(r: dict[str, Any]) -> str:
    ci = r["ci95"]
    pct = f"{r['rate']:.1%}" if r["rate"] is not None else "n/a"
    return f"{r['k']} of {r['n']} ({pct}; 95% CI {ci[0]:.1%} to {ci[1]:.1%})" if ci else pct


def render(s: dict[str, Any]) -> str:
    r1 = s["r1"]
    m = s["key_mapping"]
    ke = s["key_evidence"]
    lines = [
        "# Validation v1 score (iOS 15 public phone)",
        "",
        f"Audit run `{s['audit_run']}`, rules {s['rule_version']}, results.zip SHA-256"
        f" `{s['results_sha256']}`.",
        "",
        "## R1, the run as it stands",
        "",
        f"1. Contradicted without an expert: {_line(r1['contradicted_without_expert'])}."
        f" Claims: {', '.join(r1['contradicted_without_expert']['claims']) or 'none'}.",
        f"2. False claim shown only as support: {_line(r1['false_claim_shown_only_as_support'])}."
        f" Claims: {', '.join(r1['false_claim_shown_only_as_support']['claims']) or 'none'}.",
        f"3. Contradiction surfaced: {_line(r1['contradiction_surfaced'])}.",
        "",
        f"Key records: {m['keys']}, unmapped {len(m['unmapped'])} (listed in score.json).",
        "Key-evidence recall, per key record: retrieved"
        f" {_line(ke['key_evidence_recall_retrieved'])},"
        f" surfaced {_line(ke['key_evidence_recall_surfaced'])}.",
        "",
        "## R2, simulated expert",
        "",
        render_markdown(s["r2"]["card"]),
        "",
        "## Import counts",
        "",
        "| Kind | Mabillon | Dump |",
        "| --- | --- | --- |",
    ]
    for k, v in s["import_counts"].items():
        lines.append(f"| {k} | {v['mabillon']} | {v['dump']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, required=True, help="results.zip, or a case.db")
    ap.add_argument("--keys", type=Path, required=True, help="the folder holding the keys")
    ap.add_argument("--dump", type=Path, required=True, help="the independent dump's folder")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    s = score(a.results, a.keys, a.dump, a.out)
    print(f"scored {s['audit_run']}: see {a.out / 'score.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
