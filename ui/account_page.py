"""The Account page: who this computer is signed in as, and sign in, sign out.

Shown only while sign-in is on (account.SIGNIN_ON). It says plainly what sign-in sends and that
a license never stops a case being opened, reviewed or exported.
"""

from __future__ import annotations

from account import license as lic
from ui.pages import Page, e

SENDS = (
    "When you sign in, Mabillon opens your browser at account.getmabillon.com, where you enter "
    "your work email. After that it renews the license at most once a day when online, sending "
    "only the license id, a sign-in token and the Mabillon version. Nothing from any case is "
    "ever sent. Each request is written to ~/.mabillon/account/account.log first."
)


def _button(page: Page, action: str, label: str) -> str:
    return (
        f"<form method='post' action='{e(action)}' class='inline'>"
        f"<input type='hidden' name='token' value='{e(page.token)}'>"
        f"<button type='submit'>{e(label)}</button></form>"
    )


def account_page(page: Page, status: lic.Status, renew_note: str | None) -> str:
    err = status.state in ("invalid", "expired", "lapsed")
    head = f"<p class='flash{' err' if err else ''}' role='status'>{e(status.message)}</p>"
    note = f"<p class='muted'>{e(renew_note)}</p>" if renew_note else ""
    if status.state == "signed_out":
        actions = _button(page, "/signin/start", "Sign in")
    elif status.state == "invalid":
        actions = _button(page, "/signin/start", "Sign in again") + _button(
            page, "/signout", "Remove the saved license"
        )
    else:
        actions = _button(page, "/signout", "Sign out")
        if status.state in ("expired", "lapsed"):
            actions = _button(page, "/signin/start", "Sign in again") + actions
    body = (
        "<div class='pg-help'><h1>Account</h1>"
        f"<section class='hs'>{head}{note}<p class='actions'>{actions}</p></section>"
        "<section class='hs'><h2>What a license controls</h2>"
        "<p>Only starting a new audit. Opening Mabillon, opening a case, review, the report and "
        "export always work, signed in or not. The demo never needs a license.</p></section>"
        f"<section class='hs'><h2>What sign-in sends</h2><p>{e(SENDS)}</p></section>"
        "<section class='hs'><h2>No internet in your lab?</h2><p>Ask support for a license "
        "file, then run <code>mabillon license import &lt;file&gt;</code>. It never connects."
        "</p></section></div>"
    )
    return page.wrap("Account", body)


def done_page(signed_in: bool, message: str) -> str:
    """The browser tab the sign-in link comes back to. It is not the review screen: it holds no
    form token and nothing from a case."""
    title = "Signed in" if signed_in else "Not signed in"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{e(title)} · Mabillon</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:15vh auto;"
        "padding:0 16px;color:#1d1d1f;background:#fbfaf7}h1{font-size:1.4rem}</style>"
        f"</head><body><h1>{e(title)}</h1><p>{e(message)}</p>"
        "<p>You can close this tab.</p></body></html>"
    )
