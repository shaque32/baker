"""Synthetic case06, the held-out set for the testability step's go/no-go of record, built to
case05's design: the generator is deterministic and the committed drafts match a fresh build,
the real importer reads all three reports (with every time right across the start of daylight
saving), the key and the sheet are well formed and keep the case's design (six claims per type,
three plain and three affidavit wordings per type, a wrong reading planted for most claims),
every window follows the brief's conventions or is listed for the signer, case.json's defined
names and events match the affidavit, every check finds what the sheet expects, and a
model-free run on the draft sheet gives the drafted verdicts. Synthetic data only.

These tests hold the case itself, not a measurement made on it.
"""

import json
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.audit.assumptions import (
    TEMPLATES,
    TEMPLATES_VERSION,
    instantiate,
    parse_params,
    templates_for,
)
from core.audit.checks import CHECKS
from core.audit.rules import _REQUIRED_KIND
from core.contracts import ClaimType, GoldClaim
from core.db import apply_schema, connect
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.govdoc import PdfGovDocIngester
from eval.run_eval import load_jsonl
from eval.synthetic import case06_key as key
from eval.synthetic import case06_story as story
from eval.synthetic.case06_generate import (
    DEFAULT_OUT,
    SEED,
    affidavit_paragraphs,
    affidavit_pdf_pages,
    generate,
    write_affidavit_pdf,
)
from tests.checks.helpers import stipulate

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / DEFAULT_OUT
COMMITTED_FILES = (
    "case.json",  # pins the SHA-256 of item1.xlsx, item2.xlsx and item3.xlsx
    "affidavit_draft.md",
    "draft_gold.jsonl",
    "draft_assumptions.jsonl",
    "ANSWER_KEY_DRAFT.md",
    "SIGNING_SHEET.md",
)
IMPORTED_AT = datetime(2026, 11, 3, tzinfo=UTC)
TZ = "America/Los_Angeles"
# The one claim whose quote is in no record by design: the words in the data are similar, not
# the same (its hazard), so the claim stays unproven.
ABSENT_QUOTE = "C04"
# Earlier cases' worlds, which case06 must not reuse (case02 is never read).
EARLIER_CASES = (
    "case01_story.py",
    "case03_story.py",
    "case04_story.py",
    "case05_story.py",
    "case01_key.py",
    "case03_key.py",
    "case04_key.py",
    "case05_key.py",
)
# case06's places, agency and officer, which no earlier case may hold either.
PLACES = (
    "Sculpin",
    "Tidewrack",
    "Halyard Point",
    "Gannet Lane",
    "Kittiwake",
    "Ferrule Street",
    "Port Wendle",
    "Brackwater",
    "Aldecott",
)
PHONE_MODELS = ("Galaxy Z Flip5", "iPhone 12 mini", "DuraForce")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("case06")
    generate(out)
    return out


@pytest.fixture(scope="module")
def gold(built) -> list[GoldClaim]:
    return load_jsonl(built / "draft_gold.jsonl", GoldClaim)


@pytest.fixture(scope="module")
def sheet(built) -> list[dict]:
    text = (built / "draft_assumptions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


@pytest.fixture(scope="module")
def meta(built) -> dict:
    return json.loads((built / "case.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def imported(built, meta):
    """All three reports through the real importer, with the case's device-owner stipulations
    under the sheet's person ids."""
    conn = connect(built / "case06.db")
    apply_schema(conn)
    for s in meta["sources"]:
        importer = CellebriteExcelImporter(source_id=s["source_id"], now=IMPORTED_AT)
        src = importer.import_source(built / s["file"], conn)
        assert src.sha256 == s["sha256"], s["file"]
    stipulate(conn, key.VAR, "Emmett Varlow", key.ITEM1)
    stipulate(conn, key.COY, "Renata Coyle", key.ITEM2)
    stipulate(conn, key.PEL, "Duncan Pelloquin", key.ITEM3)
    conn.commit()
    yield conn
    conn.close()


def _record_exists(conn, rid: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM messages WHERE id = ? UNION ALL SELECT 1 FROM calls WHERE id = ? "
            "UNION ALL SELECT 1 FROM contacts WHERE id = ?",
            (rid, rid, rid),
        ).fetchone()
        is not None
    )


def _cited_texts(conn, ids) -> list[str]:
    """What a quote may come from: a message body, a saved contact's name or number, and the
    names the report shows for a cited message's sender and thread."""
    out: list[str] = []
    for rid in ids:
        for sql in (
            "SELECT body FROM messages WHERE id = ?",
            "SELECT name FROM contacts WHERE id = ?",
            "SELECT identifier FROM contacts WHERE id = ?",
            "SELECT a.display_name FROM messages m JOIN accounts a"
            " ON a.id = m.sender_account_id WHERE m.id = ?",
            "SELECT a.identifier FROM messages m JOIN accounts a"
            " ON a.id = m.sender_account_id WHERE m.id = ?",
            "SELECT t.title FROM messages m JOIN threads t ON t.id = m.thread_id WHERE m.id = ?",
        ):
            row = conn.execute(sql, (rid,)).fetchone()
            if row and row[0]:
                out.append(row[0])
    return out


# ---------------------------------------------------------------- determinism


def test_the_generator_gives_the_same_bytes_twice(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a)
    generate(b)
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(p.name for p in b.iterdir())
    assert {"item1.xlsx", "item2.xlsx", "item3.xlsx", *COMMITTED_FILES} <= set(names)
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


@pytest.mark.parametrize("name", COMMITTED_FILES)
def test_committed_outputs_match_a_fresh_generation(built, name):
    assert (built / name).read_bytes() == (COMMITTED / name).read_bytes(), (
        f"{name} is stale: run `python -m eval.synthetic.case06_generate` and commit the result"
    )


def test_case_json_pins_the_reports_and_is_not_hidden(built, meta):
    assert meta["case_id"] == "case06" and meta["synthetic"] is True
    assert meta["generator"] == "case06-gen 0.1.0"
    assert "hidden" not in meta
    assert [d["report_time"] for d in meta["devices"]] == ["utc", "local", "fixed-480"]
    assert {d["timezone"] for d in meta["devices"]} == {TZ}
    assert [d["aliases"] for d in meta["devices"]] == [
        ["CC-1", "SKIP"],
        ["CC-2"],
        ["CC-3", "DUKE", "the HAULER"],
    ]
    assert [d["names"] for d in meta["devices"]] == [["the GALAXY"], [], ["the KYOCERA"]]
    assert len({d["owner"].split()[-1] for d in meta["devices"]}) == 3  # sheet_people needs it
    from eval.synthetic.generate import sha256_file

    for s in meta["sources"]:
        assert sha256_file(built / s["file"]) == s["sha256"], s["file"]


def test_the_world_is_new(built):
    """No person, number, handle, place, phone model or time zone from case01, case03, case04
    or case05 appears in case06, and every phone number is in the 555-01xx fiction range."""
    earlier = "\n".join(
        (ROOT / "eval/synthetic" / name).read_text(encoding="utf-8") for name in EARLIER_CASES
    )
    for acct in story.ACCOUNTS.values():
        ident = acct.identifier.split("@")[0]
        assert ident not in earlier, acct.key
        assert ident[-7:] not in earlier, acct.key
        digits = ident.lstrip("+")
        if digits.isdigit() and len(digits) == 11:
            assert re.fullmatch(r"1\d{3}55501\d\d", digits), acct.key
    for name in story.PEOPLE.values():
        words = name.split(" (")[0].split()
        for word in (words[0], words[-1]):
            if word[0].isupper() and word not in ("BROKER", "Coyle's", "Instagram"):
                assert not re.search(rf"\b{re.escape(word)}\b", earlier), word
    for place in PLACES:
        assert not re.search(rf"\b{re.escape(place)}\b", earlier), place
    for model in PHONE_MODELS:
        assert model not in earlier, model
    assert "Los_Angeles" not in earlier
    affidavit = (built / "affidavit_draft.md").read_text(encoding="utf-8")
    for place in PLACES:
        assert place in affidavit, place


# ---------------------------------------------------------------- the draft key


def test_every_cited_record_exists_in_the_imported_case(imported, gold, meta):
    for g in gold:
        assert g.key_evidence, g.claim_id
        for rid in g.key_evidence:
            assert _record_exists(imported, rid), f"{g.claim_id}: {rid} missing"
    for cid, plant in meta["plants"].items():
        for rid in plant["wrong_records"]:
            assert _record_exists(imported, rid), f"{cid}: {rid} missing"


def test_the_key_and_the_sheet_are_drafts(gold, sheet):
    assert key.DRAFT_LABEL == "DRAFT (case06 builder, not signed by Arsh)"
    assert all(g.labeled_by == key.DRAFT_LABEL for g in gold)
    assert all(row["labeled_by"] == key.DRAFT_LABEL for row in sheet)


def test_every_claim_records_type_verdict_wording_and_hazard(gold, meta):
    assert [c.claim_id for c in key.CLAIMS] == [f"C{i:02d}" for i in range(1, 49)]
    assert list(key.SUMMARY) == [c.claim_id for c in key.CLAIMS]
    by_id = {g.claim_id: g for g in gold}
    for c in key.CLAIMS:
        assert c.claim_type in key.CLAIM_TYPES, c.claim_id
        assert c.wording in ("plain", "affidavit"), c.claim_id
        assert c.verdict in ("supported", "contradicted", "unproven"), c.claim_id
        assert c.hazard in key.HAZARDS, c.claim_id
        assert by_id[c.claim_id].gold_verdict.value == c.verdict
        assert by_id[c.claim_id].claim_type.value == c.claim_type
        assert by_id[c.claim_id].trap == c.hazard
        plant = meta["plants"][c.claim_id]
        assert (plant["claim_type"], plant["wording"], plant["verdict"], plant["hazard"]) == (
            c.claim_type,
            c.wording,
            c.verdict,
            c.hazard,
        )
        if c.hazard != "none":
            assert c.wrong and c.hazard_detail, f"{c.claim_id}: a hazard needs its wrong records"
        if c.wording == "affidavit":
            assert c.style, f"{c.claim_id}: say which affidavit devices the wording uses"


def test_the_design_counts(gold):
    types = Counter(c.claim_type for c in key.CLAIMS)
    assert types == {t: 6 for t in key.CLAIM_TYPES}
    for t in key.CLAIM_TYPES:
        wordings = Counter(c.wording for c in key.CLAIMS if c.claim_type == t)
        assert wordings == {"plain": 3, "affidavit": 3}, t
    verdicts = Counter(g.gold_verdict.value for g in gold)
    assert verdicts == {"supported": 24, "contradicted": 12, "unproven": 12}
    assert not key.FIRST_DRAFT_VERDICT  # the second read changed no verdict
    assert sum(c.hazard != "none" for c in key.CLAIMS) >= 24
    used = {c.hazard for c in key.CLAIMS} - {"none"}
    assert used == set(key.HAZARDS) - {"none"}  # every hazard kind is planted somewhere
    # no absence claim can be supported on a curated report
    assert not [c for c in key.CLAIMS if c.claim_type == "absence" and c.verdict == "supported"]


def test_the_second_read_answers_every_finding(built):
    ids = {c.claim_id for c in key.CLAIMS}
    assert [f.finding_id for f in key.SECOND_READ] == [f"R{i}" for i in range(1, 11)]
    for f in key.SECOND_READ:
        assert f.claims and set(f.claims) <= ids, f.finding_id
        assert f.outcome in ("fixed", "kept") and f.answer, f.finding_id
    # the reader's own sureness: two likely, eight questions
    assert [f.finding_id for f in key.SECOND_READ if f.sureness == "likely"] == ["R1", "R2"]
    sheet_md = (built / "SIGNING_SHEET.md").read_text(encoding="utf-8")
    assert f"## Second read ({key.SECOND_READ_DATE})" in sheet_md
    header = "| Finding | Claims | Reader's sureness | Builder's view | Outcome | Answer |"
    assert header in sheet_md
    for f in key.SECOND_READ:
        assert (
            f"| {f.finding_id} | {', '.join(f.claims)} | {f.sureness} | {f.severity} | "
            f"{f.outcome} |"
        ) in sheet_md
    answer_key = (built / "ANSWER_KEY_DRAFT.md").read_text(encoding="utf-8")
    assert f"The second read ({key.SECOND_READ_DATE}) changed no verdict" in answer_key


def test_the_sheet_names_the_alias_departure(built, meta):
    """SKIP and DUKE equal the first names of two people who own no phone, on purpose (the
    same-name hazard). The signing sheet says so, as a departure from the brief's naming rule."""
    sheet_md = (built / "SIGNING_SHEET.md").read_text(encoding="utf-8")
    assert "A departure from the brief's naming rule, on purpose." in sheet_md
    assert "Item 3's 'Skip' (+13605550184, Telegram user id 8820484)" in sheet_md
    assert "Item 2's 'Duke' (+12535550151)" in sheet_md
    aliases = {a for d in meta["devices"] for a in d["aliases"]}
    assert {"SKIP", "DUKE"} <= aliases
    # the two same-name people are in the reports' contacts and own no seized phone
    contacts = {
        (dev.key, name, num)
        for dev in story.DEVICES
        for name, nums in dev.contacts
        for _, num in nums
    }
    assert ("item3", "Skip", "+13605550184") in contacts
    assert ("item2", "Duke", "+12535550151") in contacts
    owners = {dev.owner for dev in story.DEVICES}
    # the note's claim lists agree with each claim's hazard label
    hazard = {c.claim_id: c.hazard for c in key.CLAIMS}
    assert all(hazard[cid] == "same_name" for cid in key.ALIAS_SAME_NAME)
    assert all(hazard[cid] == "contact_name" for cid in key.ALIAS_CONTACT_NAME)
    assert "the same-name hazard in C09, C24, C35, C39 and C45" in sheet_md
    assert "the contact-name\nhazard in C12" in sheet_md
    same_name = {story.ACCOUNTS["ten_sms"].person, story.ACCOUNTS["mar_sms"].person}
    assert same_name.isdisjoint(owners)


def test_every_alias_match_inside_a_quote_is_recorded(built, meta):
    """An alias is matched whole and in any case, so it can match a name inside a claim's
    quote. Every such claim says in the key which person the match points to, and the signing
    sheet and answer key show it."""
    aliases = [a for d in meta["devices"] for a in d["aliases"]]
    hits = set()
    for c in key.CLAIMS:
        for quote in re.findall(r'"([^"]+)"', c.text):
            for alias in aliases:
                if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", quote, re.IGNORECASE):
                    hits.add(c.claim_id)
    assert hits == set(key.ALIAS_IN_QUOTES) == {"C08", "C09", "C12", "C24"}
    sheet_md = (built / "SIGNING_SHEET.md").read_text(encoding="utf-8")
    answer_key = (built / "ANSWER_KEY_DRAFT.md").read_text(encoding="utf-8")
    for cid, line in key.ALIAS_IN_QUOTES.items():
        assert f"- {cid}: {line}" in sheet_md, cid
        assert f"- Alias inside a quote: {line}" in answer_key, cid


def test_count_rows_for_exchanged_messages_need_each_way(sheet):
    """A count claim that says "exchanged" needs a message each way (each_way); one that says
    who sent them names that side (sent_by)."""
    by_id = {c.claim_id: c for c in key.CLAIMS}
    for row in sheet:
        if row["template_id"] != "message_count":
            continue
        text = by_id[row["claim_id"]].text
        if "exchanged" in text:
            assert row["params"].get("each_way") is True, row["claim_id"]
        if " sent " in text:
            assert row["params"].get("sent_by"), row["claim_id"]


def test_claims_are_verbatim_in_their_affidavit_paragraph(built, gold):
    paras = {(p, n): text for p, n, text in affidavit_paragraphs()}
    md = (built / "affidavit_draft.md").read_text(encoding="utf-8")
    for g in gold:
        assert g.text in paras[(g.page, g.para_no)], g.claim_id
        assert f"{g.para_no}. {paras[(g.page, g.para_no)]}" in md
    words = md.casefold()
    for banned in ("guilty", "innocent", "leader", "deleted"):
        assert banned not in words, banned


def test_the_affidavit_pdf_reads_back_every_paragraph_as_written(tmp_path):
    pdf = write_affidavit_pdf(tmp_path / "affidavit.pdf")
    read = {" ".join(p.text.split()) for p in PdfGovDocIngester().parse(pdf).paragraphs}
    for _, no, text in affidavit_paragraphs():
        assert f"{no}. {' '.join(text.split())}" in read, no


def test_every_affidavit_paragraph_is_on_the_page_the_key_gives_it(tmp_path):
    """The key's page numbers are the PDF's: each paragraph fits on its page, and the ingester
    reads it there."""
    paras = affidavit_paragraphs()
    assert len(affidavit_pdf_pages()) == max(page for page, _, _ in paras)
    pdf = write_affidavit_pdf(tmp_path / "affidavit.pdf")
    pages: dict[str, set[int]] = {}
    for p in PdfGovDocIngester().parse(pdf).paragraphs:
        pages.setdefault(" ".join(p.text.split()), set()).add(p.page)
    for page, no, text in paras:
        assert pages[f"{no}. {' '.join(text.split())}"] == {page}, no


def test_quoted_text_matches_cited_records_verbatim(imported, gold, sheet):
    by_claim = {g.claim_id: g for g in gold}
    for g in gold:
        cited = _cited_texts(imported, g.key_evidence)
        for quote in re.findall(r'"([^"]+)"', g.text):
            if g.claim_id == ABSENT_QUOTE:
                continue
            assert any(quote in c for c in cited), f"{g.claim_id}: {quote!r} not cited"
    for row in sheet:
        quote = row["params"].get("quoted_text")
        if quote and row["claim_id"] != ABSENT_QUOTE:
            cited = _cited_texts(imported, by_claim[row["claim_id"]].key_evidence)
            assert any(quote in c for c in cited), f"{row['claim_id']}: {quote!r} not cited"


def test_the_absent_quote_is_in_no_record(imported, gold):
    (g,) = [g for g in gold if g.claim_id == ABSENT_QUOTE]
    assert g.gold_verdict.value == "unproven"
    for quote in re.findall(r'"([^"]+)"', g.text):
        hit = imported.execute(
            "SELECT count(*) FROM messages WHERE instr(body, ?) > 0", (quote,)
        ).fetchone()[0]
        assert hit == 0, quote


# ---------------------------------------------------------------- the draft assumption sheet


def test_every_claim_has_a_sheet_and_a_checked_core_row_unless_it_is_role_only(gold, sheet):
    """Every claim has rows. At most two role claims have only a role row; every other claim
    has a core row a deterministic check tests."""
    assert not key.NO_SHEET
    assert [s.claim_id for s in key.SHEET] == [g.claim_id for g in gold]
    types = {g.claim_id: g.claim_type.value for g in gold}
    role_only = []
    for g in gold:
        rows = [r for r in sheet if r["claim_id"] == g.claim_id]
        assert rows and any(r["is_core"] for r in rows), g.claim_id
        if {r["template_id"] for r in rows} == {"role"}:
            role_only.append(g.claim_id)
            continue
        assert any(r["is_core"] and r["expected_check"] for r in rows), g.claim_id
    assert role_only == ["C39"]
    assert all(types[cid] == "role" for cid in role_only) and len(role_only) <= 2


def test_supported_claims_carry_the_kind_their_type_needs(gold, sheet):
    for g in gold:
        need = _REQUIRED_KIND.get(ClaimType(g.claim_type))
        if g.gold_verdict.value != "supported" or need is None:
            continue
        kinds = {
            TEMPLATES[r["template_id"]].kind
            for r in sheet
            if r["claim_id"] == g.claim_id and r["is_core"]
        }
        assert need in kinds, f"{g.claim_id} needs a core {need} assumption"


def test_every_row_fits_its_template(gold, sheet):
    types = {g.claim_id: ClaimType(g.claim_type) for g in gold}
    for row in sheet:
        assert row["template_version"] == TEMPLATES_VERSION == key.TEMPLATES_VERSION
        parse_params(row["template_id"], row["params"])
        allowed = {t.id for t in templates_for(types[row["claim_id"]])}
        assert row["template_id"] in allowed, row["claim_id"]


def test_every_check_finds_what_the_sheet_expects(imported, sheet):
    accounts = {r[0] for r in imported.execute("SELECT id FROM accounts")}
    checked = 0
    for row in sheet:
        assert set(row["params"].get("account_ids", [])) <= accounts, row["claim_id"]
        if not row["expected_check"]:
            assert not TEMPLATES[row["template_id"]].checks, row["claim_id"]
            continue
        a = instantiate(row["claim_id"], row["template_id"], row["params"], row["is_core"])
        (name,) = TEMPLATES[row["template_id"]].checks
        result = CHECKS[name].run(a, imported)
        assert result.outcome.value == row["expected_check"], (row["claim_id"], result.detail)
        checked += 1
    assert checked >= 60


def test_contradicted_claims_rest_on_a_failed_core_check(gold, sheet):
    """Every contradicted claim is settled by an observed record a check can test, never by a
    model's label alone; no other claim has a failing core row."""
    failing = {r["claim_id"] for r in sheet if r["is_core"] and r["expected_check"] == "fail"}
    contradicted = {g.claim_id for g in gold if g.gold_verdict.value == "contradicted"}
    assert failing == contradicted


# ---------------------------------------------------------------- window conventions

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
NUMBERS = {"The day": 1, "Two days": 2, "Three days": 3, "two": 2, "three": 3}
_M = "(" + "|".join(MONTHS) + ")"
_W = "(" + "|".join(WEEKDAYS) + ")"
_DATE = _M + r" (\d{1,2}), (\d{4})"
_CLOCK = r"(\d{1,2})(?::(\d\d))? (a\.m\.|p\.m\.)"


def _date(month: str, d: str, y: str) -> date:
    return date(int(y), MONTHS.index(month) + 1, int(d))


def _clock(day: date, h: str, m: str | None, ampm: str) -> datetime:
    hour = int(h) % 12 + (12 if ampm == "p.m." else 0)
    return datetime(day.year, day.month, day.day, hour, int(m or 0))


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)


def _days(first: date, last: date) -> tuple[datetime, datetime]:
    return _midnight(first), _midnight(last + timedelta(days=1))


def _about(t: datetime) -> tuple[datetime, datetime]:
    return t - timedelta(minutes=8), t + timedelta(minutes=8)


def convention_window(
    head: str, gloss: str, before: str, events: dict[str, tuple[date, date]]
) -> tuple[datetime, datetime] | None:
    """The window the brief's conventions give the words `head`, as local wall clock [start,
    end), or None when no convention covers them. `events` maps each event case.json defines
    to its first and last day; `before` is the affidavit text before the claim, for a time that
    refers back ("that morning"), whose date the row's gloss names."""
    ev = "(" + "|".join(re.escape(n) for n in events) + ")"
    if m := re.fullmatch(r"[Oo]n " + _DATE, head):
        return _days(_date(*m.groups()), _date(*m.groups()))
    if m := re.fullmatch(_W + ", " + _DATE, head):
        d = _date(*m.groups()[1:])
        assert WEEKDAYS[d.weekday()] == m.group(1), head
        return _days(d, d)
    if m := re.fullmatch(
        r"(?:[Bb]etween|From) " + _M + r" (\d{1,2}) (?:and|through) " + _DATE, head
    ):
        m1, d1, m2, d2, y = m.groups()
        return _days(_date(m1, d1, y), _date(m2, d2, y))
    if m := re.fullmatch(r"At about " + _CLOCK + " on " + _DATE, head):
        return _about(_clock(_date(*m.groups()[3:]), *m.groups()[:3]))
    if m := re.fullmatch(r"At " + _CLOCK + " on " + _DATE, head):
        t = _clock(_date(*m.groups()[3:]), *m.groups()[:3])
        return t, t + timedelta(minutes=1)
    if m := re.fullmatch(r"(The day|Two days|Three days) (before|after) the " + ev, head):
        first, last = events[m.group(3)]
        n = NUMBERS[m.group(1)]
        d = first - timedelta(days=n) if m.group(2) == "before" else last + timedelta(days=n)
        return _days(d, d)
    if m := re.fullmatch(r"On the " + _W + " after the " + ev, head):
        d = events[m.group(2)][1] + timedelta(days=1)
        while WEEKDAYS[d.weekday()] != m.group(1):
            d += timedelta(days=1)
        return _days(d, d)
    if m := re.fullmatch(r"During the " + ev, head):
        return _days(*events[m.group(1)])
    if m := re.fullmatch(r"On the (two|three) days after the " + ev, head):
        last = events[m.group(2)][1]
        return _days(last + timedelta(days=1), last + timedelta(days=NUMBERS[m.group(1)]))
    if m := re.fullmatch(r"From the day after the " + ev + " through " + _DATE, head):
        return _days(events[m.group(1)][1] + timedelta(days=1), _date(*m.groups()[1:]))
    if m := re.fullmatch(
        r"(Two|Three) days before the " + ev + r" began, at about " + _CLOCK, head
    ):
        d = events[m.group(2)][0] - timedelta(days=NUMBERS[m.group(1).lower()])
        return _about(_clock(d, *m.groups()[2:]))
    if m := re.fullmatch(
        r"On the night of the " + ev + r", between (\d{1,2}) (a\.m\.|p\.m\.) and (\d{1,2}) "
        r"(a\.m\.|p\.m\.)",
        head,
    ):
        first = events[m.group(1)][0]
        start = _clock(first, m.group(2), None, m.group(3))
        end = _clock(first, m.group(4), None, m.group(5))
        if end <= start:  # the night runs past midnight
            end += timedelta(days=1)
        return start, end + timedelta(minutes=1)
    if m := re.fullmatch(r"At about " + _CLOCK + " that (morning|night)", head):
        (g,) = re.findall(_DATE, gloss)
        day = _date(*g)
        assert f"{g[0]} {g[1]}, {g[2]}" in before, head  # the date it refers back to
        return _about(_clock(day, *m.groups()[:3]))
    return None


def _utc_strings(start: datetime, end: datetime) -> tuple[str, str]:
    zone = ZoneInfo(TZ)
    s = start.replace(tzinfo=zone).astimezone(UTC)
    e = end.replace(tzinfo=zone).astimezone(UTC) - timedelta(microseconds=1)
    return (
        s.isoformat().replace("+00:00", "Z"),
        e.isoformat(timespec="microseconds").replace("+00:00", "Z"),
    )


def _events(meta: dict) -> dict[str, tuple[date, date]]:
    return {
        e["name"]: (
            date.fromisoformat(e["first_day"]),
            date.fromisoformat(e.get("last_day", e["first_day"])),
        )
        for e in meta["events"]
    }


def _listed_non_convention(sheet_md: str) -> set[tuple[str, str]]:
    section = sheet_md.split("## Windows that follow no convention", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| (C\d\d) \| `(\w+)` \|", section, re.MULTILINE))


def test_every_window_follows_a_convention_or_is_listed_for_the_signer(built, sheet, meta):
    """Each window is recomputed from the claim's own words under the brief's conventions and
    compared to the microsecond. The windows no convention covers are exactly the ones
    SIGNING_SHEET.md lists, and each of their rows gives the examiner's reasoning."""
    events = _events(meta)
    texts = {c.claim_id: c.text for c in key.CLAIMS}
    paragraph_of = {}
    for _, _, text in affidavit_paragraphs():
        for cid, ctext in texts.items():
            if ctext in text:
                paragraph_of[cid] = text
    unparsed: set[tuple[str, str]] = set()
    convention = 0
    for row in sheet:
        w = row["params"].get("window")
        if not w:
            continue
        cid = row["claim_id"]
        assert w["tz"] == TZ, cid
        head, _, gloss = w["raw"].partition(" (")
        assert head in texts[cid], (cid, head)  # the words are the claim's own
        para = paragraph_of[cid]
        before = para[: para.index(texts[cid])]
        got = convention_window(head, gloss, before, events)
        if got is None:
            unparsed.add((cid, row["template_id"]))
            assert key.NON_CONVENTION[cid] in row["note"], cid
            continue
        assert (w["start_utc"], w["end_utc"]) == _utc_strings(*got), (cid, w["raw"])
        convention += 1
    sheet_md = (built / "SIGNING_SHEET.md").read_text(encoding="utf-8")
    assert unparsed == _listed_non_convention(sheet_md)
    assert {cid for cid, _ in unparsed} == set(key.NON_CONVENTION)
    assert convention >= 40


def test_the_conventions_read_the_brief_examples():
    """The convention reader gives the brief's own examples."""
    assert _about(datetime(2025, 3, 1, 23, 50)) == (
        datetime(2025, 3, 1, 23, 42),
        datetime(2025, 3, 1, 23, 58),
    )
    events = {"SEARCH": (date(2025, 3, 12), date(2025, 3, 12))}
    assert convention_window("Two days before the SEARCH", "", "", events) == _days(
        date(2025, 3, 10), date(2025, 3, 10)
    )
    assert convention_window("Between March 20 and March 23, 2025", "", "", events) == (
        datetime(2025, 3, 20),
        datetime(2025, 3, 24),
    )
    assert convention_window("Shortly before the SEARCH", "", "", events) is None


def test_the_night_the_clocks_went_forward_is_read_in_real_hours(sheet):
    """Across the jump from 2 to 3 a.m. on March 9, wall-clock windows are four real hours,
    not five: C30's 11 p.m. to 4 a.m. and C34's hour before the jump."""
    by_claim = {r["claim_id"]: r for r in sheet if r["params"].get("window")}
    c30 = by_claim["C30"]["params"]["window"]
    assert (c30["start_utc"], c30["end_utc"]) == (
        "2025-03-09T07:00:00Z",
        "2025-03-09T11:00:59.999999Z",
    )
    c34 = by_claim["C34"]["params"]["window"]
    assert (c34["start_utc"], c34["end_utc"]) == (
        "2025-03-09T09:00:00Z",
        "2025-03-09T09:59:59.999999Z",
    )


# ---------------------------------------------------------------- what the affidavit defines


def _norm(name: str) -> str:
    return re.sub(r"^the ", "", " ".join(name.split()), flags=re.IGNORECASE).casefold()


def _defines(text: str, name: str) -> bool:
    term = re.sub(r"^the ", "", name)
    return f'"{term}"' in text


def test_case_json_names_and_events_match_the_affidavit(meta, imported):
    """Each alias, phone name, number name and event in case.json is defined in exactly one
    affidavit paragraph, each event's defining words appear in exactly one paragraph, every
    named number is held by an account in the reports, and nothing the affidavit defines in
    quotes is missing from case.json."""
    paras = [text for _, _, text in affidavit_paragraphs()]
    aliases = [a for d in meta["devices"] for a in d["aliases"]]
    phones = [n for d in meta["devices"] for n in d["names"]]
    numbers = [n for entry in meta["numbers"] for n in entry["names"]]
    events = [e["name"] for e in meta["events"]]
    for name in (*aliases, *phones, *numbers, *events):
        assert sum(_defines(p, name) for p in paras) == 1, name
    for d in meta["devices"]:
        owner_surname = d["owner"].split()[-1].upper()
        for name in (*d["aliases"], *d["names"]):
            (para,) = [p for p in paras if _defines(p, name)]
            assert owner_surname in para, (name, d["owner"])
    held = {r[0] for r in imported.execute("SELECT identifier FROM accounts")}
    for entry in meta["numbers"]:
        (para,) = [p for p in paras if _defines(p, entry["names"][0])]
        assert entry["identifier"] in para, entry
        ident = entry["identifier"]
        digits = re.sub(r"[^\d+]", "", ident)
        assert digits in held, entry
    for e in meta["events"]:
        holding = [p for p in paras if e["defined_as"] in p]
        assert len(holding) == 1, e["name"]
        assert f'{e["defined_as"]} (the "{e["name"]}")' in holding[0], e["name"]
        first = date.fromisoformat(e["first_day"])
        days = [first]
        if "last_day" in e:
            last = date.fromisoformat(e["last_day"])
            assert last > first, e["name"]
            days.append(last)
        for d in days:
            assert f"{MONTHS[d.month - 1]} {d.day}, {d.year}" in holding[0], (e["name"], d)
    # everything the opening paragraphs define in quotes is in case.json, or is a phone
    # owner's surname, or names a person who owns no seized phone (the BROKER)
    defined = set()
    for p in paras[:8]:
        defined |= set(re.findall(r'"([A-Z][A-Z0-9 -]*[A-Z0-9])"', p))
    owners = {d["owner"].split()[-1].upper() for d in meta["devices"]}
    entered = {re.sub(r"^the ", "", n) for n in (*aliases, *phones, *numbers, *events)}
    assert defined == entered | owners | {"BROKER"}


def test_no_defined_name_serves_two_things(meta):
    """No alias, phone name, number name or event name equals another, or a phone owner's
    name, first name or surname, with or without a leading "the"."""
    names = [
        *(a for d in meta["devices"] for a in d["aliases"]),
        *(n for d in meta["devices"] for n in d["names"]),
        *(n for entry in meta["numbers"] for n in entry["names"]),
        *(e["name"] for e in meta["events"]),
    ]
    normed = [_norm(n) for n in names]
    assert len(normed) == len(set(normed)), Counter(normed).most_common(3)
    people = set()
    for d in meta["devices"]:
        parts = d["owner"].split()
        people |= {_norm(d["owner"]), _norm(parts[0]), _norm(parts[-1])}
    assert not set(normed) & people


# ---------------------------------------------------------------- the plants hold


def _reserved(text: str) -> list[str]:
    return _reserved_stem(text) + _reserved_word(text)


def _reserved_stem(text: str) -> list[str]:
    folded = text.casefold()
    return [w for w in story.RESERVED_STEMS if re.search(rf"(?<!\w){re.escape(w)}", folded)]


def _reserved_word(text: str) -> list[str]:
    folded = text.casefold()
    return [w for w in story.RESERVED_WORDS if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", folded)]


def test_background_chatter_never_uses_a_reserved_word():
    for pool in (*story.POOLS.values(), story.IG_CUSTOMER, story.IG_SHOP):
        for phrase in pool:
            assert not _reserved(phrase), phrase
    msgs, _ = story.make_filler(SEED)
    assert len(msgs) > 1000
    assert not [m.body for m in msgs if _reserved(m.body)]


def test_background_chatter_never_holds_a_claim_or_sheet_quote(sheet):
    quotes = {q for c in key.CLAIMS for q in re.findall(r'"([^"]+)"', c.text)}
    quotes |= {r["params"]["quoted_text"] for r in sheet if r["params"].get("quoted_text")}
    msgs, _ = story.make_filler(SEED)
    for m in msgs:
        assert not [q for q in quotes if q.casefold() in m.body.casefold()], m.body


def test_background_chatter_never_joins_two_subjects():
    subjects = {"varlow", "coyle", "pelloquin", "broker"}
    msgs, calls = story.make_filler(SEED)
    acc = story.ACCOUNTS
    for m in msgs:
        assert not (acc[m.sender].person in subjects and acc[m.to].person in subjects), m.key
    for c in calls:
        assert not (acc[c.caller].person in subjects and acc[c.callee].person in subjects), c.key


def test_records_left_off_a_phone_are_on_the_other(imported):
    """The second_phone plants: a record one report does not hold is on the other phone."""
    for m in story.SCRIPTED_MESSAGES:
        for dev in m.skip:
            n = imported.execute(
                "SELECT count(*) FROM messages WHERE source_id = ? AND body = ? AND ts_utc = ?",
                (dev, m.body, m.at.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ).fetchone()[0]
            assert n == 0, (m.key, dev)
            others = imported.execute(
                "SELECT count(*) FROM messages WHERE source_id != ? AND body = ? AND ts_utc = ?",
                (dev, m.body, m.at.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ).fetchone()[0]
            assert others >= 1, m.key
    for c in story.SCRIPTED_CALLS:
        for dev in c.skip:
            n = imported.execute(
                "SELECT count(*) FROM calls WHERE source_id = ? AND ts_utc = ?",
                (dev, c.at.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ).fetchone()[0]
            assert n == 0, (c.key, dev)


def test_every_record_imports_at_its_story_time_on_every_phone(imported):
    """Each phone prints time its own way (Item 1 UTC+0, Item 2 local with its offset, Item 3 a
    fixed UTC-8) and the importer gets every scripted record back to the same UTC instant,
    either side of the jump from 2 to 3 a.m. on March 9."""
    printed = {"item1": 0, "item3": -480}
    for m in story.SCRIPTED_MESSAGES:
        ts = m.at.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = imported.execute(
            "SELECT source_id, ts_offset_min FROM messages WHERE body = ? AND ts_utc = ?",
            (m.body, ts),
        ).fetchall()
        assert rows, m.key
        for source_id, offset in rows:
            want = printed.get(source_id, story.pacific_offset_min(m.at))
            assert offset == want, (m.key, source_id)
    for c in story.SCRIPTED_CALLS:
        ts = c.at.strftime("%Y-%m-%dT%H:%M:%SZ")
        n = imported.execute(
            "SELECT count(*) FROM calls WHERE ts_utc = ? AND duration_s = ?", (ts, c.duration_s)
        ).fetchone()[0]
        assert n >= 1, c.key
    jump = datetime(2025, 3, 9, 10, tzinfo=UTC)  # 2 a.m. PST, which became 3 a.m. PDT
    night = [m for m in story.SCRIPTED_MESSAGES if abs(m.at - jump) < timedelta(hours=2)]
    offsets = {story.pacific_offset_min(m.at) for m in night}
    assert offsets == {-480, -420}, "scripted records on both sides of the jump"
    for m in night:
        assert m.at.astimezone(story.ZONE).hour != 2, m.key  # 2 to 3 a.m. never happened


# ---------------------------------------------------------------- the model-free run


def test_a_model_free_run_on_the_draft_sheet_gives_the_drafted_verdicts(tmp_path, monkeypatch):
    from eval import run_pipeline

    monkeypatch.chdir(ROOT)
    spec = COMMITTED / "draft_assumptions.jsonl"
    preds = run_pipeline.run_once("case06", "model-free", "accept", tmp_path, spec, "simulated")
    got = {p.claim_id: p.verdict.value for p in preds}
    want = {c.claim_id: c.verdict for c in key.CLAIMS}
    assert got == want
