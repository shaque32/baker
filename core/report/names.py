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

import html
import re
import sqlite3

# An id starts after a space, a quote or a bracket, never inside another id
# (stip:device_owner:dev:item1 stays whole). A sentence's closing period is not part of it.
_CASE_ID = re.compile(
    r"(?<![\w:])(?:acct:[^\s'\"(),]+|person:[\w.:-]+|dev:[\w.-]+)(?<!\.)", re.IGNORECASE
)
_COUNT_OP = re.compile(r"\b(eq|ge|le|gt|lt) (?=\d)")
_COUNT_WORD = {
    "eq": "exactly",
    "ge": "at least",
    "le": "at most",
    "gt": "more than",
    "lt": "fewer than",
}


def _e(text: str) -> str:
    return html.escape(text)


def _plain(text: str) -> str:
    return _e(_COUNT_OP.sub(lambda c: _COUNT_WORD[c[1]] + " ", text))


class Names:
    """Shows a case's ids by name and remembers each name it showed, for the report's key."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # each id shown, once whatever its case (a check writes acct:item1:telegram:5551234)
        self.used: dict[str, tuple[str, str]] = {}  # lowercased id -> (id, the name shown)

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
        sql = (
            "SELECT name FROM persons WHERE id = ? COLLATE NOCASE"
            if token.lower().startswith("person:")
            else "SELECT label FROM devices WHERE id = ? COLLATE NOCASE"
        )
        row = self.conn.execute(sql, (token,)).fetchone()
        return row[0] if row and row[0] else token

    def html(self, text: str | None) -> str:
        """The text as HTML, each id shown by name with the id in its hover title, and the count
        operators (eq, ge, ...) in words."""
        if not text:
            return ""
        out, at = [], 0
        for m in _CASE_ID.finditer(text):
            out.append(_plain(text[at : m.start()]))
            shown = self.name(m[0])
            if shown == m[0]:
                out.append(_e(m[0]))
            else:
                self.used.setdefault(m[0].lower(), (m[0], shown))
                out.append(f"<span title='{_e(m[0])}'><span class=\"q\">{_e(shown)}</span></span>")
            at = m.end()
        out.append(_plain(text[at:]))
        return "".join(out)

    def key_table(self) -> str:
        """Each name the report showed, with the id it stands for, so a printed copy stays
        traceable. Empty when no id was shown by name."""
        if not self.used:
            return ""
        rows = "".join(
            f'<tr><td><span class="q">{_e(shown)}</span></td><td class="mono">{_e(i)}</td></tr>'
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
