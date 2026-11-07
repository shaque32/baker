"""The case's ids shown by name, for the review screen and the report.

An assumption's text, a check's search line or a rule's reason names people, phones and
accounts by their case ids (person:dev:item1:owner, dev:item1, acct:item1:Telegram:5551234).
Names shows each one as the case names it: a person by the name the expert's stipulation gives
them, a phone by its label, an account as its app and identifier (one account held on two
phones once). The id stays in the hover title, and the report prints a key from each name back
to its id (key_table), so a printed copy stays traceable. Display only: the stored text, the
rules and the audit log keep the ids. A name is the case's text, so it goes through q() and the
forbidden-word check leaves it as written.
"""

from __future__ import annotations

import copy
import re
import sqlite3
from collections.abc import Callable

from core import db
from core.report.fmt import e, q

# An id starts after a space, a quote or a bracket, never inside another id
# (stip:device_owner:dev:item1 stays whole). A sentence's closing period is not part of it.
_CASE_ID = re.compile(
    r"(?<![\w:])(?:acct:[^\s'\"(),]+|person:[\w.:-]+|dev:[\w.-]+)(?<!\.)", re.IGNORECASE
)
# Only the filler's own count wording ("holds eq 13 messages"), so quoted record text that
# happens to read "lt 3" stays verbatim.
_COUNT_OP = re.compile(r"(?<=\bholds )(eq|ge|le|gt|lt) (?=\d)")
_COUNT_WORD = {
    "eq": "exactly",
    "ge": "at least",
    "le": "at most",
    "gt": "more than",
    "lt": "fewer than",
}


# Words in quotes inside Mabillon's own sentence: an assumption's text or a rule's reason
# ("The words \"Done. It's been deleted.\" mean ...") carries the claim's quoted message, and a
# filler refusal prints the words it was given as Python writes them, in single quotes
# ("'PETROV deleted the WhatsApp messages ...' is not inside quotation marks in the claim"). A
# single quote counts only where no letter or digit touches it on the outside, so an
# apostrophe ("PETROV's") never opens or closes one. The kinds nest (a rule's reason holds
# 'The words "..." mean ...'), so each is matched on its own and only cited spans are kept.
_QUOTED = re.compile(r'"([^"]+)"|\u201c([^\u201d]+)\u201d')
_SINGLE = re.compile(r"(?<![\w'])'([^']+)'(?![\w'])")


def _fold(text: str) -> str:
    """Case, curly quotes and runs of spaces do not count: a check's search line prints the
    claim's words lowercased."""
    text = text.translate(str.maketrans("\u2018\u2019\u201c\u201d", "''\"\""))
    return " ".join(text.casefold().split())


def _plain(text: str) -> str:
    return e(_COUNT_OP.sub(lambda c: _COUNT_WORD[c[1]] + " ", text))


class Names:
    """Shows a case's ids by name and remembers each name it showed, for the report's key."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # each id shown, once whatever its case (a check writes acct:item1:telegram:5551234)
        self.used: dict[str, tuple[str, str]] = {}  # lowercased id -> (id, the name shown)
        self._claims: list[str] | None = None

    def for_claim(self, claim_text: str) -> Names:
        """These names, citing quoted words only from this one claim: for the lines that
        belong to it (its assumptions, checks and verdict reasons). The key of names shown
        stays shared with the report."""
        scoped = copy.copy(self)
        scoped._claims = [_fold(claim_text)]
        return scoped

    def _cited(self, words: str) -> bool:
        """True when the words stand in the claim (for_claim), or else in one of the case's
        claims, verbatim and as whole words: the document's words, not Mabillon's (validation
        run 3, where a claim quoting "It's been deleted." stopped the report). A one-word quote
        counts ('The words "leader" mean ...'), but never inside a longer word ("undeleted")."""
        if self._claims is None:
            try:
                rows = self.conn.execute("SELECT text FROM claims")
                self._claims = [_fold(r[0]) for r in rows]
            except db.OperationalError:  # a table built without claims (tests)
                self._claims = []
        folded = _fold(words)
        if not folded:
            return False
        whole = re.compile(rf"(?<!\w){re.escape(folded)}(?!\w)")
        return any(whole.search(c) for c in self._claims)

    def _account(self, aid: str) -> str:
        row = self.conn.execute(
            "SELECT app, identifier FROM accounts WHERE id = ? COLLATE NOCASE", (aid,)
        ).fetchone()
        if row:
            return f"{row[0]} {row[1]}"
        parts = aid.split(":", 3)
        return f"{parts[2]} {parts[3]}" if len(parts) == 4 else aid

    def name(self, token: str) -> str:
        if token.lower().startswith("acct:"):
            ids = re.split(r"/(?=acct:)", token, flags=re.IGNORECASE)
            return " / ".join(dict.fromkeys(self._account(a) for a in ids))
        person = token.lower().startswith("person:")
        sql = (
            "SELECT name FROM persons WHERE id = ? COLLATE NOCASE"
            if person
            else "SELECT label FROM devices WHERE id = ? COLLATE NOCASE"
        )
        row = self.conn.execute(sql, (token,)).fetchone()
        if not row or not row[0]:
            return token
        same = (
            "SELECT COUNT(*) FROM persons WHERE name = ?"
            if person
            else "SELECT COUNT(*) FROM devices WHERE label = ?"
        )
        # two people (or phones) the case names alike keep their ids beside the name
        shared = self.conn.execute(same, (row[0],)).fetchone()[0] > 1
        return f"{row[0]} ({token})" if shared else row[0]

    def html(self, text: str | None) -> str:
        """The text as HTML, each id shown by name with the id in its hover title, the count
        operators (eq, ge, ...) in words, and words it quotes from a claim as cited."""
        return self._quotes(text, self._ids)

    def cite(self, text: str | None) -> str:
        """The text as HTML exactly as written (ids stay ids), with only the words it quotes
        from a claim marked as cited: for the stored reasons under Technical details."""
        return self._quotes(text, e)

    def _quotes(self, text: str | None, rest: Callable[[str], str]) -> str:
        if not text:
            return ""
        cited = sorted(
            (m.start(), -m.end(), m[0], words)
            for pattern in (_QUOTED, _SINGLE)
            for m in pattern.finditer(text)
            if self._cited(words := next(g for g in m.groups() if g))
        )  # quoted words no claim holds stay Mabillon's own, checked whole
        out, at = [], 0
        for start, neg_end, whole, words in cited:
            if start < at:
                continue  # inside a cited span already kept (the earlier, longer one)
            out += [rest(text[at:start]), e(whole[0]), q(words), e(whole[-1])]
            at = -neg_end
        out.append(rest(text[at:]))
        return "".join(out)

    def _ids(self, text: str) -> str:
        out, at = [], 0
        for m in _CASE_ID.finditer(text):
            out.append(_plain(text[at : m.start()]))
            shown = self.name(m[0])
            if shown == m[0]:
                out.append(e(m[0]))
            else:
                self.used.setdefault(m[0].lower(), (m[0], shown))
                out.append(f"<span title='{e(m[0])}'>{q(shown)}</span>")
            at = m.end()
        out.append(_plain(text[at:]))
        return "".join(out)

    def key_table(self) -> str:
        """Each name the report showed, with the id it stands for, so a printed copy stays
        traceable. Empty when no id was shown by name."""
        if not self.used:
            return ""
        rows = "".join(
            f'<tr><td>{q(shown)}</td><td class="mono">{e(i)}</td></tr>'
            for i, shown in sorted(self.used.values(), key=lambda v: (v[1].lower(), v[0]))
        )
        return (
            "<h2>Names used in this report</h2><p>Claims, checks and verdict traces name "
            "people, phones and accounts as the case names them. Each name stands for the case "
            "id below, which the rules and the audit log use.</p><table><thead><tr>"
            f"<th>Name</th><th>Case id</th></tr></thead>{rows}</table>"
        )


def plain_ids(conn: sqlite3.Connection, text: str) -> str:
    """One text with the case's ids shown by name (the review screen's helper)."""
    return Names(conn).html(text)
