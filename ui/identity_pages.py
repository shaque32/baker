"""The Identities page of the review screen: who is behind each name the government document uses.

Every person in the case (each phone owner the expert stipulated, and each name the expert
added from the document) gets a card with the links code proposed between them and an account,
and the records for and against each link (core/identity/links.py). The expert confirms,
rejects or leaves each link unresolved, or links an account themselves. Only a confirmed link
counts in a check; the others stay unknown. Nothing here is decided by a model.

A pure function of the case database, like ui/pages.py. Names and record text are cited text
and go through q(), so the forbidden-word check can tell them from the tool's own words.
"""

from __future__ import annotations

import sqlite3

from core import pipeline
from core.identity import aliases
from core.identity import links as L
from ui.pages import Page, _folded, e, link, q

STATUS_LABEL = {
    "proposed": "Proposed",
    "unresolved": "Unresolved",
    "confirmed": "Confirmed by the expert",
    "rejected": "Rejected",
}


def note_html(note: str) -> str:
    """A note from core/identity/links.py, with the case's own words shown as cited text."""
    out, rest = [], note
    while L.CITE_OPEN in rest:
        before, _, after = rest.partition(L.CITE_OPEN)
        cited, _, rest = after.partition(L.CITE_CLOSE)
        out.append(e(before) + q(cited))
    return "".join(out) + e(rest)


def _ref(s: L.Signal) -> str:
    where = f"{s.source_id} {s.locator}".strip()
    return f"<div class='ref mono'>{e(where)} · {e(s.record_id)}</div>"


def _signals(items: list[L.Signal], empty: str, shown: int | None = None) -> str:
    """The records on one side of a link. The first `shown` stay open; the rest fold under
    them, so a long side does not bury the decision. Every record stays on the page."""
    if not items:
        return f"<p class='muted'>{e(empty)}</p>"
    rows = [
        f"<li><div class='quote'>{q(s.quote)}</div><div class='note'>{note_html(s.note)}</div>"
        f"{_ref(s)}</li>"
        for s in items
    ]
    if shown is None or len(rows) <= shown + 1:
        return "<ul class='sig'>" + "".join(rows) + "</ul>"
    rest = len(rows) - shown
    return (
        "<ul class='sig'>"
        + "".join(rows[:shown])
        + "</ul><details class='sigmore'><summary>"
        + f"{rest} more record{'s' if rest != 1 else ''}</summary><ul class='sig'>"
        + "".join(rows[shown:])
        + "</ul></details>"
    )


def _side(cls: str, title: str, n: int) -> str:
    return f"<p class='side {cls}'>{e(title)} <span class='n'>{n}</span></p>"


def _decided(row: dict) -> str:
    if not row["decided_by"]:
        return ""
    return (
        f"<p class='muted'>{e(STATUS_LABEL[row['status']])} by {e(row['decided_by'])}, "
        f"{e(row['decided_at_utc'])}.</p>"
    )


def _link_card(
    page: Page, case: L.Case, person: L.Person, row: dict, cand: L.Candidate | None
) -> str:
    status = row["status"]
    group = next((g for g in case.groups.values() if row["account_id"] in g.account_ids), None)
    label = group.label if group else row["account_id"]
    phones = (
        ", ".join(sorted({case.data.accounts[a].source_id for a in group.account_ids}))
        if group
        else ""
    )
    tier = "b-conf" if status == "confirmed" else "b-open"
    tier_text = "confirmed" if status == "confirmed" else "inferred"
    stated = L.claims_stating(case, cand) if cand else []
    seen = f" · Seen on {q(phones)}." if phones else ""
    out = [
        f"<article class='card idlink st-{e(status)}' id='{e(row['id'])}'><div class='in'>",
        f"<div class='idhead'><p class='idpair'>{q(label)} "
        f"<span class='arrow' aria-label='linked to'>→</span> {q(person.name)}</p>"
        f"<span class='idtags'><span class='badge {tier}'>{e(tier_text)}</span>"
        f"<span class='stpill st-{e(status)}'>{e(STATUS_LABEL[status])}</span></span></div>",
        f"<p class='idmeta'>Account used by person{seen}</p>",
        f"<p class='idbasis'>{note_html(cand.basis) if cand else q(row['basis'])}</p>",
    ]
    if stated:
        names = ", ".join(f"<a href='{e(link('/claim', id=c))}'>{e(c)}</a>" for c in stated)
        out.append(
            f"<p class='caution'>The document states this link itself, in {names}. Confirming "
            "it here does not decide that claim: it still needs evidence you accept there. "
            "Confirm only what the records show.</p>"
        )
    out.append(_decided(row))
    out.append("</div>")
    if cand is not None:
        grid = (
            "<div class='idgrid'><div>"
            + _side("for", "For", len(cand.support))
            + _signals(cand.support, "No record names this account this way now.", 3)
            + "</div><div>"
            + _side("against", "Against, or pointing elsewhere", len(cand.against))
            + _signals(cand.against, "None found in the records searched.", 3)
            + "</div></div>"
        )
        if status in ("confirmed", "rejected"):  # decided: the records fold, one click away
            grid = (
                f"<details class='idrec'><summary>Records: {len(cand.support)} for, "
                f"{len(cand.against)} against or pointing elsewhere</summary>{grid}</details>"
            )
        out.append(grid)
        if cand.mentions:
            out.append(
                f"<div class='in'><details><summary>Messages in this account's conversations "
                f"that use these names ({len(cand.mentions)}). Context, not labeled.</summary>"
                + _signals(cand.mentions, "")
                + "</details></div>"
            )
    choices = "".join(
        f"<button type='submit' name='status' value='{v}'"
        f"{' class=primary' if v == 'confirmed' else ''}"
        f"{' aria-pressed=true' if status == v else ''}>{t}</button>"
        for v, t in (
            ("confirmed", "Confirm"),
            ("rejected", "Reject"),
            ("unresolved", "Leave unresolved"),
        )
    )
    out.append(
        "<div class='in idact'>"
        + page.form(
            "/identity/decide",
            f"<input type='hidden' name='id' value='{e(row['id'])}'>"
            "<label>Why (one sentence; needed to confirm or reject)"
            "<input type='text' name='note' maxlength='300' class='wide'></label>"
            f"<span class='choices'>{choices}</span>",
            "plain decide",
            "/identities",
            anchor=row["id"],
        )
        + "</div></article>"
    )
    return "".join(out)


def _person_card(
    conn: sqlite3.Connection, page: Page, case: L.Case, person: L.Person, rows: list[dict]
) -> str:
    owner = [case.device_labels.get(d, d) for d in person.devices]
    kind = (
        f"Phone owner, by stipulation ({', '.join(owner)})"
        if owner
        else f"Named in the document, added by {person.created_by}"
    )
    claims = L.claims_naming(conn, person)
    named = (
        "Claims that use this name: "
        + ", ".join(f"<a href='{e(link('/claim', id=c))}'>{e(c)}</a>" for c, _ in claims)
        + "."
        if claims
        else "No claim uses this name as the audit reads it (whole name or surname)."
    )
    cands = {c.account_id: c for c in L.candidates(case, person)}
    by_group = {
        a: c for c in cands.values() for a in c.group.account_ids
    }  # a stored link may point at another phone's copy
    remove = (
        page.form(
            "/person/remove",
            f"<input type='hidden' name='id' value='{e(person.id)}'>"
            "<button type='submit' class='remove'>Remove this person</button>",
            "inline",
            "/identities",
        )
        if not owner and not any(r["status"] == "confirmed" for r in rows)
        else ""
    )
    owner_note = (
        "The owner accounts of this phone are tied to this person by the "
        "stipulation. Links below are other accounts that carry the name."
    )
    out = [
        f"<section class='person' id='{e(person.id)}'><div class='phead'><div>"
        f"<h2 class='pname'>{q(person.name)}</h2><p class='pkind'>{e(kind)}</p></div>"
        f"{remove}</div>",
        f"<p class='pclaims'>{named}</p>",
        page.form(
            "/person/aliases",
            f"<input type='hidden' name='id' value='{e(person.id)}'>"
            "<label>Also called in the document "
            "<input type='text' name='aliases' maxlength='600' placeholder='SUBJECT-1, HAL' "
            f"value='{e(', '.join(_stored_aliases(conn, person.id)))}'></label> "
            "<button type='submit'>Save names</button>"
            "<span class='muted hint'> Separate names with commas. Each is matched whole, and "
            "every report lists the names you gave.</span>",
            "plain aliasf",
            "/identities",
            anchor=person.id,
        ),
    ]
    if owner and rows:
        out.append(f"<p class='muted pnote'>{owner_note}</p>")
    for row in rows:
        out.append(_link_card(page, case, person, row, by_group.get(row["account_id"])))
    if not rows and owner:
        out.append(
            "<details class='absent'><summary>No account beyond this phone's own carries this "
            "name or a part of it.</summary>"
            f"<p>{note_html(L.searched_note(case))}</p><p>{owner_note}</p></details>"
        )
    elif not rows:
        out.append(
            _folded(
                "<div class='banner'><strong>No account in the data carries this name or a part "
                f"of it.</strong> {note_html(L.searched_note(case))} Not found does not mean "
                f"{q(person.name)} has no account here: a name can be saved differently, or not "
                "at all. Claims that rest on who this person is stay unproven unless you link an "
                "account below.</div>"
            )
        )
    out.append("</section>")
    return "".join(out)


def _stored_aliases(conn: sqlite3.Connection, person_id: str) -> list[str]:
    """The person's aliases as recorded, a shared one included, so the form shows them all."""
    return [a.alias for a in aliases.stored(conn) if a.person_id == person_id]


def _unplaced(page: Page, names: list[L.UnplacedName], persons: list[L.Person]) -> str:
    if not names:
        return (
            "<p class='muted'>Every capitalised name in the claims, and every name the claim "
            "reader proposed, resolves to exactly one person.</p>"
        )
    out = ["<ul class='ledger unplaced'>"]
    for u in names:
        cl = ", ".join(f"<a href='{e(link('/claim', id=c))}'>{e(c)}</a>" for c in u.claim_ids)
        why = (
            "matches no person, so the audit cannot test what it says about them"
            if u.matches == 0
            else f"matches {u.matches} people, so the audit refuses it as ambiguous"
        )
        add = (
            page.form(
                "/person/add",
                f"<input type='hidden' name='name' value='{e(u.name)}'>"
                "<button type='submit'>Add as a person</button>",
                "inline",
                "/identities",
            )
            if u.matches == 0
            else ""
        )
        if u.matches == 0 and persons:
            opts = "".join(f"<option value='{e(p.id)}'>{e(p.name)}</option>" for p in persons)
            add += page.form(
                "/person/alias/add",
                f"<input type='hidden' name='alias' value='{e(u.name)}'>"
                f"<select name='id' aria-label='Person'>{opts}</select> "
                "<button type='submit'>Add as another name</button>",
                "inline",
                "/identities",
            )
        out.append(
            f"<li><div class='row'><div class='head'><div class='text'>{q(u.name)}</div>"
            f"<div class='acts'>{add}</div></div><div class='needs'>Used in {cl}; {e(why)}.</div>"
            "</div></li>"
        )
    out.append("</ul>")
    return "".join(out)


def _changed_since_audit(conn: sqlite3.Connection) -> int:
    run = pipeline.last_run(conn)
    if run is None:
        return 0
    return conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE at_utc > ? AND action IN"
        " ('identity.decide', 'identity.link', 'person.add', 'person.remove',"
        " 'person.alias.add', 'person.alias.remove')",
        (run["started_at_utc"],),
    ).fetchone()[0]


def identities_page(conn: sqlite3.Connection, page: Page) -> str:
    case = L.load(conn)
    rows_by_person: dict[str, list[dict]] = {p.id: [] for p in case.persons}
    for r in conn.execute(
        "SELECT id, account_id, person_id, status, tier, basis, decided_by, decided_at_utc"
        " FROM identity_links ORDER BY person_id, status = 'rejected', id"
    ):
        row = dict(
            zip(
                (
                    "id",
                    "account_id",
                    "person_id",
                    "status",
                    "tier",
                    "basis",
                    "decided_by",
                    "decided_at_utc",
                ),
                r,
                strict=True,
            )
        )
        rows_by_person.setdefault(row["person_id"], []).append(row)
    counts = {s: 0 for s in STATUS_LABEL}
    for rows in rows_by_person.values():
        for r in rows:
            counts[r["status"]] += 1
    out = [
        "<h1>Who is behind each name</h1>",
        "<p class='lede'>Each proposed link between an account and a person shows the records "
        "for and against it. Nothing is merged: a link counts in the audit's checks only after "
        "you confirm it.</p>",
        "<details class='more'><summary>How links are proposed and used</summary>"
        "<p>Code proposes a link only where the extraction itself puts a form of the person's "
        "name on the account; no model is involved. Every report lists each confirmed link as "
        "a limitation. Proposed, unresolved and rejected links stay unknown. A proposed or "
        "unresolved link only widens what the audit searches for that person.</p></details>",
        "<div class='idbar'><div class='counts'>"
        + "".join(
            f"<span class='stpill st-{s}{' zero' if not n else ''}'>{e(STATUS_LABEL[s])} "
            f"<b>{n}</b></span>"
            for s, n in counts.items()
        )
        + "</div>"
        + page.form(
            "/identity/look",
            "<button type='submit'>Look for links again</button> <span class='muted'>After "
            "importing more data or changing a phone owner.</span>",
            "plain look",
            "/identities",
        )
        + "</div>",
    ]
    changed = _changed_since_audit(conn)
    if changed:
        out.append(
            _folded(
                f"<div class='banner'><strong>{changed} identity change(s) since the last audit "
                "started.</strong> They reach the checks and searches on the next audit run. "
                "Finished model work is reused, so only what changed goes to the model. "
                "<a href='/setup'>Set up and run</a>. Re-running the verdicts alone does not "
                "apply them.</div>"
            )
        )
    out.append("<h2>Names the claims use with no person yet</h2>")
    out.append(_unplaced(page, L.unplaced_names(conn, case.persons), case.persons))
    out.append(
        page.form(
            "/person/add",
            "<label>Add a person, written as the document writes the name "
            "<input type='text' name='name' required maxlength='120' "
            "placeholder='The name as printed'></label> <button type='submit'>Add person</button>"
            "<p class='muted'>Adding a name ties it to nothing. Mabillon then looks for accounts "
            "that carry the name and proposes links for you to decide.</p>",
            "plain addp",
            back="/identities",
        )
    )
    owners = [p for p in case.persons if p.devices]
    others = [p for p in case.persons if not p.devices]
    if not case.persons:
        out.append(
            "<p>No person in this case yet. Stipulate who used each phone on "
            "<a href='/setup'>Set up and run</a>, and add the names the document uses above.</p>"
        )
    for p in [*others, *owners]:
        out.append(_person_card(conn, page, case, p, rows_by_person.get(p.id, [])))
    if case.persons and case.groups:
        accounts = sorted(case.groups.values(), key=lambda g: g.label.casefold())
        acc_opts = "".join(
            f"<option value='{e(g.account_ids[0])}'>{e(g.label)}"
            f"{' · ' + e(g.names[0].text) if g.names else ''}</option>"
            for g in accounts
        )
        per_opts = "".join(f"<option value='{e(p.id)}'>{e(p.name)}</option>" for p in case.persons)
        out.append(
            "<h2>Link an account yourself</h2>"
            + page.form(
                "/identity/link",
                f"<p class='pick'><label>Account <select name='account'>{acc_opts}</select>"
                f"</label> <label>Person <select name='person'>{per_opts}</select></label></p>"
                "<p><label>Why (one sentence, recorded with your name)<input type='text' "
                "name='note' required maxlength='300' class='wide'></label></p>"
                "<p class='go'><button type='submit' class='primary'>Link and confirm</button> "
                "<span class='muted'>Your own link is your decision, so it is confirmed at "
                "once and listed in the report as a limitation.</span></p>",
                "box linkself",
                back="/identities",
            )
        )
    return page.wrap("Identities", "<div class='pg-ids'>" + "".join(out) + "</div>")
