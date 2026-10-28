"""Score the validation-v1 run (eval/validation/PREREGISTERED.md), once, with the code at main.

    python -m eval.validation.score_hickman --results results.zip --keys DIR --dump DIR --out DIR

--keys holds the signed answer keys (gold.jsonl, gold_b2.jsonl, gold_b3.jsonl) and --dump the
independent ElementTree dump of the phone's report.xml (eval/validation/dump_ufdr.py). Both stay
in project files. The run's case.db is copied; the copy is scored and the original never changes.

1. Key evidence: each key record (`ufdr:source_index:N`) is matched to Mabillon's records by
   content, since Mabillon's ids are positional and keep no UFDR id. A message must agree on its
   raw time (the same report.xml text both sides read), its app and its body; a call on its raw
   time, its app, its duration and its parties; a contact on its name and one of its
   identifiers (a phone number by its last ten digits). A key with no single match (none,
   several, or a kind Mabillon does not cite, such as a chat) is listed, never matched to a
   near miss.
2. R1, the run as it stands: the three primary measures, key-evidence recall (counted per key
   record, so a contact Mabillon keeps as one row per identifier still counts once), label counts.
3. R2, the simulated expert (eval/simulated_expert.py) on the mapped keys, then the rules again
   (`mabillon redecide`), scored by eval/validation/card.py.
4. Import counts beside the dump's.
5. Coverage, for run 2's low-coverage rule (eval/validation/PREREGISTERED_v2.md): k, the claims
   the run tested (not marked "Not tested"), out of all; each refusal kind that left a claim
   untested, with its claims; and measures 1 to 3 and the R2 card again over tested claims only.
   These are added beside the measures above and change none of them.
6. For run 3's plan (eval/validation/PREREGISTERED_v3.md): each tested claim's tier, code-checked
   (a core assumption went to a deterministic check, whatever its outcome) or expert only, with
   the plan's minimum on the code-checked tier; and, beside measures 1 to 3, the claims a failed
   check contradicted although gold does not.
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
# 1.0.0: #134. 1.1.0: coverage (#142). 1.2.0: a claim is tested only with a first-pass verdict,
# coverage must account for every gold claim, and refusal kinds match whole refusal phrases.
# 1.3.0: run 3's tiers (code-checked or expert only) and false Contradicted from a failed check.
SCORER_VERSION = "1.3.0"

# Run 2's low-coverage rule 3: below this many tested claims, no accuracy claim.
MINIMUM_TESTED = 30
INSUFFICIENT = "insufficient coverage, no accuracy claim"
# Run 3's minimum (PREREGISTERED_v3.md), counted on the code-checked tier only.
MINIMUM_CODE_CHECKED = 30

# What the assumption filler refused, by kind, read from each untested claim's "Not tested"
# sentence (the run keeps no other per-claim record of it). A claim counts once per kind it
# has; a claim can have several. The kinds follow the filler's own refusal wording.
REFUSAL_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("phone not matched to a device", re.compile(r"phone '.*?' matches \d+ devices")),
    (
        "phone time zone not known",
        re.compile(r"unknown phone time zone|do not share one known time zone"),
    ),
    (
        "person not set up by the expert",
        re.compile(r"matches (?:no person|\d+ persons) the expert created"),
    ),
    ("account not found", re.compile(r"matches no account in the case")),
    ("channel not named or not in the case", re.compile(r"name the channel|not an app in")),
    (
        "time range not plainly stated",
        re.compile(
            r"window ends before it starts|window longer than \d+ days"
            r"|the document states no year for this range"
            r"|the stated time range is not a plain range on one day"
            r"|window (?:start|end) is not near (?:the (?:start|end) of the stated time range"
            r"|a time the range states)"
            r"|a weekday the document gives is not that date's weekday"
            r"|a range offset from a date|a range 'after' a date starts at midnight"
            r"|window (?:start|end) \S+ is not a date the claim states"
            r"|window end is not on a date the claim states"
            r"|a range with no time of day must (?:start|end) at midnight"
            r"|the claim's range for no contact is not a plain stated range"
            r"|the time range is not one the claim plainly states"
            r"|the window's words are not written in the claim"
            r"|window start or end is not 'YYYY-MM-DDTHH:MM'"
            r"|window times must be wall-clock|the range does not say UTC"
            r"|record_time from the claim's date"
        ),
    ),
    (
        "count or duration not readable",
        re.compile(
            r"the claim's count is approximate or strict"
            r"|is not written in the claim as a number of messages or calls"
            r"|cannot read the duration|the duration '.*?' is a bound"
            r"|cannot read the number in|the duration's words are not written in the claim"
        ),
    ),
    ("value not written in the claim", re.compile(r"(?:quoted_text|'.*?') is not written in")),
    (
        "model output not usable",
        re.compile(
            r"not valid JSON|wrong shape|JSON is not an object|model output|model returned"
            r"|model has no run id|is not allowed for this claim|does not take handles"
        ),
    ),
)
UNCLASSIFIED = "none of the kinds above (see the claim's sentence)"
# A claim the run neither decided nor marked "Not tested" (it is missing from the run, or the
# run stopped short): untested, never scored right or wrong.
NO_VERDICT = "no verdict recorded"
ONLY_SUMMARY = "no refusal listed, only the filler's summary of what was missing"
# The filler's closing summary of a claim ("no usable X assumption; the claim stays unproven")
# says what is missing, not why, so it is not read for kinds.
_SUMMARY_END = "the claim stays unproven"
# A refusal's own "; " (the sentence joins refusals with "; " too): what follows it.
_CONTINUED = re.compile(r"(?:the claim stays unproven|it cannot be checked|name the phone)\b")
_MORE = re.compile(r"\s*\(and \d+ more\)")


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
            "SELECT c.id, f.identifier, t.identifier FROM calls c"
            " LEFT JOIN accounts f ON f.id = c.from_account_id"
            " LEFT JOIN accounts t ON t.id = c.to_account_id"
            " WHERE c.ts_raw = ? AND c.app = ? AND c.duration_s IS ?",
            (rec["time_utc"], _app(rec, chats), _seconds(rec.get("duration"))),
        ).fetchall()
        # Every party Mabillon put on the call must be one of the record's parties, from Parties,
        # From or To (by number, or by name for a party with none). A call with no parties on
        # either side, because the source did not say who called whom, is matched on the other
        # fields alone.
        named = {
            _ident(v)
            for p in (*rec.get("parties", []), *rec.get("from", []), *rec.get("to", []))
            for v in (p.get("id"), p.get("name"))
            if v
        }
        ids = [r[0] for r in rows if not named or {_ident(v) for v in r[1:] if v} <= named]
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


def _code_checked(conn: sqlite3.Connection, manifest: dict, claim_id: str) -> bool:
    """True when a core assumption of the claim went to a deterministic check in this run,
    whatever the outcome: run 3's code-checked tier. A claim with no such check is expert only."""
    for cid in manifest.get(claim_id, {}).get("checks", []):
        row = conn.execute(
            "SELECT a.is_core FROM check_results c JOIN assumptions a ON a.id = c.assumption_id"
            " WHERE c.id = ?",
            (cid,),
        ).fetchone()
        if row and row[0]:
            return True
    return False


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


def _measure(
    per_claim: dict[str, dict[str, Any]],
    name: str,
    base,  # noqa: ANN001
    hit,  # noqa: ANN001
) -> dict[str, Any]:
    rows = {c: r for c, r in per_claim.items() if base(r)}
    hits = sorted(c for c, r in rows.items() if hit(r))
    by_type: dict[str, dict[str, Any]] = {}
    for t in sorted({r["type"] for r in rows.values()}):
        of_t = [c for c, r in rows.items() if r["type"] == t]
        by_type[t] = rate(sum(c in hits for c in of_t), len(of_t))
    return {"measure": name, **rate(len(hits), len(rows)), "claims": hits, "by_type": by_type}


def _measures(per_claim: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Primary measures 1 to 3 over the claims given."""
    contra = Verdict.CONTRADICTED.value
    return {
        "contradicted_without_expert": _measure(
            per_claim,
            "R1 contradicted, gold not contradicted",
            lambda r: r["gold"] != contra,
            lambda r: r["r1"] == contra,
        ),
        "false_claim_shown_only_as_support": _measure(
            per_claim,
            "gold contradicted; supports items, no contradicts item, no failed check",
            lambda r: r["gold"] == contra,
            lambda r: r["supports"] > 0 and r["contradicts"] == 0 and not r["failed_checks"],
        ),
        "contradiction_surfaced": _measure(
            per_claim,
            "gold contradicted; a failed check or a contradicts item on a key record",
            lambda r: r["gold"] == contra,
            lambda r: bool(r["failed_checks"]) or r["contradicts_on_key"] > 0,
        ),
        # Run 3's added measure: a failed deterministic check decided a wrong Contradicted.
        "contradicted_by_failed_check": _measure(
            per_claim,
            "R1 contradicted with a failed check, gold not contradicted",
            lambda r: r["gold"] != contra,
            lambda r: r["r1"] == contra and bool(r["failed_checks"]),
        ),
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
            "code_checked": _code_checked(conn, manifest, g.claim_id),
            "supports": sum(e.stance is Stance.SUPPORTS for e in items),
            "contradicts": sum(e.stance is Stance.CONTRADICTS for e in items),
            "contradicts_on_key": sum(
                e.stance is Stance.CONTRADICTS and e.record_id in key for e in items
            ),
        }
    return {
        **_measures(per_claim),
        "no_r1_verdict": sorted(c for c, r in per_claim.items() if r["r1"] is None),
        "per_claim": per_claim,
    }


def refusals(sentence: str) -> list[str]:
    """The refusals one claim's "Not tested" sentence lists (pipeline.not_tested_reason)."""
    text = sentence.partition("Refused:")[2].strip().removesuffix(".")
    parts: list[str] = []
    for piece in _MORE.sub("", text).split("; "):
        if parts and _CONTINUED.match(piece):
            parts[-1] += "; " + piece
        elif piece.strip():
            parts.append(piece.strip())
    return parts


def refusal_kinds(sentence: str) -> list[str]:
    """The refusal kinds in one claim's "Not tested" sentence, in REFUSAL_KINDS order. Each
    refusal is read on its own, and one that matches no kind adds UNCLASSIFIED, so no refusal
    is dropped. A claim with nothing but the closing summary is ONLY_SUMMARY."""
    found: set[str] = set()
    for refusal in refusals(sentence):
        if refusal.endswith(_SUMMARY_END):
            continue
        hits = [name for name, pattern in REFUSAL_KINDS if pattern.search(refusal)]
        found.update(hits or [UNCLASSIFIED])
    order = [name for name, _ in REFUSAL_KINDS] + [UNCLASSIFIED]
    return [name for name in order if name in found] or [ONLY_SUMMARY]


def coverage(run: dict, gold: list[GoldClaim], r1: dict[str, Any]) -> dict[str, Any]:
    """Run 2's low-coverage rule: k tested of all claims, why the rest were not, and measures
    1 to 3 again over tested claims only (rules 1 and 2). A claim is tested only when it has a
    first-pass verdict and is not marked "Not tested"; it fails closed. An untested claim is
    listed by id with its sentence, never counted correct or wrong."""
    not_tested: dict[str, str] = run.get("not_tested") or {}
    per_claim = r1["per_claim"]
    ids = [g.claim_id for g in gold]
    if len(set(ids)) != len(ids) or set(per_claim) != set(ids):
        raise SystemExit("score: coverage needs each gold claim once, with its first-pass row")
    untested = {
        c: not_tested[c] if c in not_tested else f"{NO_VERDICT}."
        for c in ids
        if c in not_tested or per_claim[c]["r1"] is None
    }
    tested = [c for c in ids if c not in untested]
    if len(tested) + len(untested) != len(gold):
        raise SystemExit(f"score: coverage counts {len(tested) + len(untested)} of {len(gold)}")
    kinds: dict[str, list[str]] = {name: [] for name, _ in REFUSAL_KINDS}
    kinds[UNCLASSIFIED] = []
    kinds[ONLY_SUMMARY] = []
    kinds[NO_VERDICT] = []
    for c, sentence in untested.items():
        for kind in [NO_VERDICT] if c not in not_tested else refusal_kinds(sentence):
            kinds[kind].append(c)
    k = len(tested)
    # Run 3's tiers. A row without the field (a scorer before 1.3.0) counts as expert only.
    code_checked = [c for c in tested if per_claim[c].get("code_checked")]
    return {
        "claims": len(ids),
        "tested": k,
        "untested": len(untested),
        "minimum": MINIMUM_TESTED,
        "result": "enough tested claims" if k >= MINIMUM_TESTED else INSUFFICIENT,
        "refusal_kinds": {name: {"claims": len(cs), "ids": cs} for name, cs in kinds.items() if cs},
        # A sentence shows at most four refusals; its kinds may then be undercounted.
        "sentences_cut_short": [c for c, sentence in untested.items() if _MORE.search(sentence)],
        "untested_claims": untested,
        "tested_claims": tested,
        "r1_over_tested": _measures({c: per_claim[c] for c in tested}),
        "tiers": {
            "code_checked": code_checked,
            "expert_only": [c for c in tested if c not in code_checked],
        },
        "minimum_code_checked": MINIMUM_CODE_CHECKED,
        "result_v3": (
            "enough code-checked claims"
            if len(code_checked) >= MINIMUM_CODE_CHECKED
            else INSUFFICIENT
        ),
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


def r2(db: Path, run: dict, mapped: list[GoldClaim], tested: list[str]) -> dict[str, Any]:
    """The simulated expert on the mapped keys, then the rules again, scored by the card: over
    all claims, and again over the tested claims only (run 2's low-coverage rule 2)."""
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
    checks = load_checks(db, [g.claim_id for g in mapped])
    card = build_card(mapped, preds, verdicts, checks)
    over_tested = build_card([g for g in mapped if g.claim_id in tested], preds, verdicts, checks)
    return {
        "run_id": again.run_id,
        "simulated_expert": decided.summary(),
        "card": card,
        "card_over_tested": over_tested,
    }


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
    covered = coverage(run, mapped, r1)

    result = {
        "scorer_version": SCORER_VERSION,
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
        "coverage": covered,
        "r2": r2(db, run, mapped, covered["tested_claims"]),
    }
    (out / "score.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    (out / "score.md").write_text(render(result), encoding="utf-8")
    return result


def _line(r: dict[str, Any]) -> str:
    ci = r["ci95"]
    if not ci:  # no claims in the base
        return f"{r['k']} of {r['n']}"
    return f"{r['k']} of {r['n']} ({r['rate']:.1%}; 95% CI {ci[0]:.1%} to {ci[1]:.1%})"


def _r1_lines(r1: dict[str, Any]) -> list[str]:
    return [
        f"1. Contradicted without an expert: {_line(r1['contradicted_without_expert'])}."
        f" Claims: {', '.join(r1['contradicted_without_expert']['claims']) or 'none'}.",
        f"2. False claim shown only as support: {_line(r1['false_claim_shown_only_as_support'])}."
        f" Claims: {', '.join(r1['false_claim_shown_only_as_support']['claims']) or 'none'}.",
        f"3. Contradiction surfaced: {_line(r1['contradiction_surfaced'])}.",
        *(
            [
                "4. Contradicted by a failed check, gold not contradicted (run 3):"
                f" {_line(r1['contradicted_by_failed_check'])}."
                f" Claims: {', '.join(r1['contradicted_by_failed_check']['claims']) or 'none'}."
            ]
            if "contradicted_by_failed_check" in r1
            else []
        ),
    ]


def _coverage_lines(c: dict[str, Any], card: dict[str, Any]) -> list[str]:
    lines = [
        "## Coverage (run 2's low-coverage rule, eval/validation/PREREGISTERED_v2.md)",
        "",
        f"**Tested: {c['tested']} of {c['claims']} claims.** Minimum {c['minimum']}:"
        f" {c['result']}.",
        "",
    ]
    if "tiers" in c:
        t = c["tiers"]
        lines += [
            f"**Run 3 (eval/validation/PREREGISTERED_v3.md): code-checked {len(t['code_checked'])},"
            f" expert only {len(t['expert_only'])}.** Minimum {c['minimum_code_checked']}"
            f" code-checked: {c['result_v3']}.",
            "",
            f"Expert only: {', '.join(t['expert_only']) or 'none'}.",
            "",
        ]
    if c["refusal_kinds"]:
        lines += [
            "Why the untested claims were not tested (a claim counts once per kind it has):",
            "",
            "| Refusal kind | Claims |",
            "| --- | --- |",
        ]
        lines += [f"| {k} | {v['claims']} |" for k, v in c["refusal_kinds"].items()]
        lines.append("")
    if c["sentences_cut_short"]:
        lines += [
            "These claims' sentences list only their first four refusals, so a kind may be"
            f" undercounted: {', '.join(c['sentences_cut_short'])}.",
            "",
        ]
    lines += [
        "### Measures over tested claims only (the ones run 2 reports)",
        "",
        *_r1_lines(c["r1_over_tested"]),
        "",
        render_markdown(card),
        "",
    ]
    if c["untested_claims"]:
        lines += ["### Untested claims (never counted correct or wrong)", ""]
        lines += [f"- {cid}: {why}" for cid, why in c["untested_claims"].items()]
        lines.append("")
    return lines


def render(s: dict[str, Any]) -> str:
    r1 = s["r1"]
    m = s["key_mapping"]
    ke = s["key_evidence"]
    lines = [
        "# Validation v1 score (iOS 15 public phone)",
        "",
        f"Audit run `{s['audit_run']}`, rules {s['rule_version']}, results.zip SHA-256"
        f" `{s['results_sha256']}`, scorer {s.get('scorer_version', 'before 1.2.0')}.",
        "",
    ]
    if "coverage" in s:
        lines += _coverage_lines(s["coverage"], s["r2"]["card_over_tested"])
    lines += [
        "## R1, the run as it stands (all claims, as plan v1 defines it)",
        "",
        *_r1_lines(r1),
        "",
        f"Key records: {m['keys']}, unmapped {len(m['unmapped'])} (listed in score.json).",
        "Key-evidence recall, per key record: retrieved"
        f" {_line(ke['key_evidence_recall_retrieved'])},"
        f" surfaced {_line(ke['key_evidence_recall_surfaced'])}.",
        "",
        "## R2, simulated expert (all claims, as plan v1 defines it)",
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
