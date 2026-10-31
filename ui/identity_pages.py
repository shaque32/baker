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
from core.identity import links as L
from ui.pages import Page, e, link, q

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


def _signals(items: list[L.Signal], empty: str) -> str:
    if not items:
        return f"<p class='muted'>{e(empty)}</p>"
    return (
        "<ul class='sig'>"
        + "".join(
            f"<li><div class='quote'>{q(s.quote)}</div><div>{note_html(s.note)}</div>{_ref(s)}</li>"
            for s in items
        )
        + "</ul>"
    )


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
    out = [
        f"<article class='card idlink st-{e(status)}' id='{e(row['id'])}'><div class='in'>",
        "<div class='idhead'><span class='eyebrow'>Account used by person</span><span>"
        f"<span class='badge {tier}'>{e(tier_text)}</span>"
        f"<span class='stpill st-{e(status)}'>{e(STATUS_LABEL[status])}</span></span></div>",
        f"<p class='idpair'>{q(label)} <span class='arrow' aria-label='linked to'>→</span> "
        f"{q(person.name)}</p>",
        f"<p class='muted'>Seen on {q(phones)}.</p>" if phones else "",
        f"<p>{note_html(cand.basis) if cand else q(row['basis'])}</p>",
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
        out.append(
            "<div class='idgrid'><div><p class='side for'>For</p>"
            + _signals(cand.support, "No record names this account this way now.")
            + "</div><div><p class='side against'>Against, or pointing elsewhere</p>"
            + _signals(cand.against, "None found in the records searched.")
            + "</div></div>"
        )
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
        "<div class='in'>"
        + page.form(
            "/identity/decide",
            f"<input type='hidden' name='id' value='{e(row['id'])}'>"
            "<label>Why (one sentence; needed to confirm or reject)<br>"
            "<input type='text' name='note' maxlength='300' class='wide'></label><br>" + choices,
            "plain",
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
    out = [
        f"<section class='person' id='{e(person.id)}'><p class='eyebrow'>{e(kind)}</p>",
        f"<h2 class='pname'>{q(person.name)}</h2><p>{named}</p>",
    ]
    if owner:
        out.append(
            "<p class='muted'>The owner accounts of this phone are tied to this person by the "
            "stipulation. Links below are other accounts that carry the name.</p>"
        )
    for row in rows:
        out.append(_link_card(page, case, person, row, by_group.get(row["account_id"])))
    if not rows and owner:
        out.append(
            "<p class='muted'>No account beyond this phone's own carries this name or a part "
            f"of it. {note_html(L.searched_note(case))}</p>"
        )
    elif not rows:
        out.append(
            "<div class='banner'><strong>No account in the data carries this name or a part of "
            f"it.</strong> {note_html(L.searched_note(case))} Not found does not mean "
            f"{q(person.name)} has no account here: a name can be saved differently, or not at "
            "all. Claims that rest on who this person is stay unproven unless you link an "
            "account below.</div>"
        )
    if not owner and not any(r["status"] == "confirmed" for r in rows):
        out.append(
            page.form(
                "/person/remove",
                f"<input type='hidden' name='id' value='{e(person.id)}'>"
                "<button type='submit'>Remove this person</button>",
                "inline",
                "/identities",
            )
        )
    out.append("</section>")
    return "".join(out)


def _unplaced(page: Page, names: list[L.UnplacedName]) -> str:
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
        out.append(
            f"<li><div class='row'><div class='head'><div class='text'>{q(u.name)}</div>"
            f"<div>{add}</div></div><div class='needs'>Used in {cl}; {e(why)}.</div>"
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
        " ('identity.decide', 'identity.link', 'person.add', 'person.remove')",
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
        "<div class='counts'>"
        + "".join(
            f"<span class='stpill st-{s}'>{e(STATUS_LABEL[s])} <b>{n}</b></span>"
            for s, n in counts.items()
        )
        + "</div>",
    ]
    changed = _changed_since_audit(conn)
    if changed:
        out.append(
            f"<div class='banner'><strong>{changed} identity change(s) since the last audit "
            "started.</strong> They reach the checks and searches on the next audit run. "
            "Finished model work is reused, so only what changed goes to the model. "
            "<a href='/setup'>Set up and run</a>. Re-running the verdicts alone does not apply "
            "them.</div>"
        )
    out.append("<h2>Names the claims use with no person yet</h2>")
    out.append(_unplaced(page, L.unplaced_names(conn, case.persons)))
    out.append(
        page.form(
            "/person/add",
            "<label>Add a person, written as the document writes the name "
            "<input type='text' name='name' required maxlength='120' "
            "placeholder='The name as printed'></label> <button type='submit'>Add person</button>"
            "<p class='muted'>Adding a name ties it to nothing. Mabillon then looks for accounts "
            "that carry the name and proposes links for you to decide.</p>",
            back="/identities",
        )
    )
    out.append(
        page.form(
            "/identity/look",
            "<button type='submit'>Look for links again</button> <span class='muted'>After "
            "importing more data or changing a phone owner.</span>",
            "plain",
            "/identities",
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
                f"<p><label>Account <select name='account'>{acc_opts}</select></label> "
                f"<label>Person <select name='person'>{per_opts}</select></label></p>"
                "<p><label>Why (one sentence, recorded with your name)<br><input type='text' "
                "name='note' required maxlength='300' class='wide'></label></p>"
                "<button type='submit' class='primary'>Link and confirm</button> "
                "<span class='muted'>Your own link is your decision, so it is confirmed at "
                "once and listed in the report as a limitation.</span>",
                back="/identities",
            )
        )
    return page.wrap("Identities", "".join(out))
