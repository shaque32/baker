"""How the filler finds the account a claim means when the words are not the account's own
identifier: a number written another way, a person the expert created, or the display name of
exactly one account. Synthetic case01 and made-up wording only.
"""

import sqlite3

import pytest

from core.audit.assumption_filler import (
    Reject,
    _Account,
    _same_number,
    phone_digits,
)
from core.audit.assumptions import parse_params
from core.audit.checks._common import Account
from core.contracts import ClaimType
from eval.synthetic.generate import generate
from tests.checks.helpers import stipulate
from tests.test_affidavit_wording import QUOTE, claim, filler, proposal

PETROV, REYES = "person:petrov", "person:reyes"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    generate(out, out / "case01.db")
    c = sqlite3.connect(out / "case01.db")
    stipulate(c, PETROV, "Daniel Petrov", "dev:item1")
    stipulate(c, REYES, "Marcus Reyes", "dev:item2")
    c.execute("PRAGMA foreign_keys = OFF")
    yield c
    c.close()


def sender(words: str, app: str) -> dict:
    return {"people": [], "accounts": [{"as_written": words, "app": app}]}


@pytest.mark.parametrize(
    ("words", "digits"),
    [
        ("(212) 555-0122", "12125550122"),
        ("212-555-0122", "12125550122"),
        ("212.555.0122", "12125550122"),
        ("+1 212 555 0122", "12125550122"),
        ("+1 (212) 555-0122", "12125550122"),
        ("1-212-555-0122", "12125550122"),
        ("+44 20 7946 0958", "442079460958"),
        ("555-0122", None),  # no area code
        ("2125550122x", None),
        ("012-555-0122", None),  # not a North American number, and no "+"
        ("20 7946 0958", None),  # a country it does not write
        ("2125550122", None),  # digits run together: no form to read the country from
        ("(919)888-7386", "19198887386"),
        ("ThisIs DfirTwo", None),
    ],
)
def test_phone_digits_reads_only_plain_numbers(words, digits):
    assert phone_digits(words) == digits


def _acc(app: str, ident: str) -> Account:
    return Account(id="a", source_id="s", device_id=None, app=app, identifier=ident,
                   display_name=None)  # fmt: skip


def test_a_user_id_made_of_digits_is_never_a_phone_number():
    assert _same_number("12125550122", _acc("Signal", "+1 212-555-0122"))
    assert _same_number("12125550122", _acc("WhatsApp", "12125550122@s.whatsapp.net"))
    assert _same_number("12125550122", _acc("Phone", "+1 212 555 0122"))
    assert not _same_number("12125550122", _acc("Telegram", "2125550122"))  # a user id
    assert not _same_number("12125550122", _acc("Telegram", "12125550122"))


@pytest.mark.parametrize(
    ("words", "app", "found"),
    [
        ("(212) 555-0122", "SMS", {"acct:item1:SMS:+12125550122", "acct:item2:SMS:+12125550122"}),
        ("212-555-0122", "WhatsApp", {"acct:item1:WhatsApp:12125550122@s.whatsapp.net",
                                      "acct:item2:WhatsApp:12125550122@s.whatsapp.net"}),
        ("+1 212 555 0122", "Phone", {"acct:item1:Phone:+12125550122",
                                      "acct:item2:Phone:+12125550122"}),
    ],
)  # fmt: skip
def test_a_number_written_another_way_finds_its_account(conn, words, app, found):
    acc = _Account.model_validate({"as_written": words, "app": app})
    assert filler(conn)._accounts(acc, [], f"PETROV wrote to {words} on {app}.") == found


def test_a_number_alone_never_picks_an_app_the_claim_does_not_name(conn):
    # WhatsApp holds the number too, but the claim says "called", not WhatsApp
    acc = _Account.model_validate({"as_written": "(212) 555-0122", "app": "WhatsApp"})
    with pytest.raises(Reject, match="matches no account"):
        filler(conn)._accounts(acc, [], "Item 1 called (212) 555-0122.")


def test_a_number_on_an_app_that_does_not_hold_it_is_still_refused(conn):
    acc = _Account.model_validate({"as_written": "(212) 555-0122", "app": "Telegram"})
    with pytest.raises(Reject, match="matches no account"):
        filler(conn)._accounts(acc, [], "PETROV wrote to (212) 555-0122 on Telegram.")


def test_a_number_two_accounts_recorded_differently_share_is_refused(conn):
    # WhatsApp holds 12125550122@s.whatsapp.net; the same number recorded as "+1 212 555 0122"
    # on the same app is another account until an expert links them
    conn.execute(
        "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier,"
        " display_name) VALUES ('acct:extra:wa', 'src:none', 'extra/wa', NULL, 'WhatsApp',"
        " '+1 212 555 0122', NULL)"
    )
    try:
        acc = _Account.model_validate({"as_written": "212-555-0122", "app": "WhatsApp"})
        with pytest.raises(Reject, match="is the number of 2 WhatsApp accounts"):
            filler(conn)._accounts(acc, [], "PETROV wrote to 212-555-0122 on WhatsApp.")
    finally:
        conn.execute("DELETE FROM accounts WHERE id = 'acct:extra:wa'")


def test_a_shared_number_is_not_looked_up_again_as_a_display_name(conn):
    # Codex on #152: the refusal was caught, and the display name of one of the two accounts
    # then picked it.
    conn.execute(
        "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier,"
        " display_name) VALUES ('acct:extra:wa2', 'src:none', 'extra/wa2', NULL, 'WhatsApp',"
        " '+1 212 555 0122', '212-555-0122')"
    )
    try:
        text = f'On March 18, 2026, 212-555-0122 wrote "{QUOTE}" on WhatsApp.'
        with pytest.raises(Reject, match="is the number of 2 WhatsApp accounts"):
            filler(conn)._resolve(claim(text), "", proposal(
                "sender", **sender("212-555-0122", "WhatsApp")))  # fmt: skip
    finally:
        conn.execute("DELETE FROM accounts WHERE id = 'acct:extra:wa2'")


@pytest.mark.parametrize("words", ["Reyes D", "+12125550199"])  # a display name, an identifier
def test_no_count_or_absence_is_read_on_the_accounts_of_an_app_that_holds_more(conn, words):
    # Native Messages holds iMessages and SMS together. Codex on #153: an account found on it
    # with no channel named let a count of iMessages count SMS too. However the account was
    # found, a count or an absence on it is refused when the claim names a narrower kind.
    conn.execute(
        "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier,"
        " display_name) VALUES ('acct:extra:nm', 'src:none', 'extra/nm', NULL,"
        " 'Native Messages', '+12125550199', 'Reyes D')"
    )
    try:
        acc = [{"as_written": words, "app": "Native Messages"}]
        count = "On January 9, 2026, PETROV sent 3 iMessages to Reyes D (+12125550199)."
        with pytest.raises(Reject, match="no count or absence is read on its accounts"):
            filler(conn)._resolve(claim(count, ClaimType.COUNT), "", proposal(
                "message_count", quoted_text="", accounts=acc, count={"value": 3}))  # fmt: skip
        absence = "On January 9, 2026, PETROV exchanged no iMessages with Reyes D (+12125550199)."
        with pytest.raises(Reject, match="no count or absence is read on its accounts"):
            filler(conn)._resolve(claim(absence, ClaimType.ABSENCE), "", proposal(
                "no_contact", quoted_text="", accounts=acc))  # fmt: skip
        if words.startswith("+"):  # "messages" names both kinds (and no app, for a name)
            # (A count one side sent is refused anyway: the count check counts both ways.)
            messages = "On January 9, 2026, PETROV and Reyes D (+12125550199) exchanged 3 messages."
            out = filler(conn)._resolve(claim(messages, ClaimType.COUNT), "", proposal(
                "message_count", quoted_text="", accounts=acc, count={"value": 3}))  # fmt: skip
            assert out.params["account_ids"] == ["acct:extra:nm"]
    finally:
        conn.execute("DELETE FROM accounts WHERE id = 'acct:extra:nm'")


def test_a_person_written_as_an_account_is_that_person(conn):
    text = f'On March 18, 2026, PETROV wrote "{QUOTE}" on Instagram.'
    out = filler(conn)._resolve(claim(text), "", proposal(
        "sender", **sender("PETROV", "Instagram")))  # fmt: skip
    assert out.params["person_ids"] == [PETROV]
    assert "account_ids" not in out.params
    # the app the person is written on scopes their accounts (Codex on #152): a message of
    # theirs on another app does not do
    assert out.params["channels"] == ["Instagram"]


def test_a_person_on_an_app_the_claim_does_not_name_or_the_channels_leave_out_is_refused(conn):
    text = f'On March 18, 2026, PETROV wrote "{QUOTE}".'
    with pytest.raises(Reject, match="does not name the channel"):
        filler(conn)._resolve(claim(text), "", proposal(
            "sender", **sender("PETROV", "Instagram")))  # fmt: skip
    text = f'On March 18, 2026, PETROV wrote "{QUOTE}" on Instagram or Telegram.'
    with pytest.raises(Reject, match="channels leave out"):
        filler(conn)._resolve(claim(text), "", proposal(
            "sender", channels=["Telegram"], **sender("PETROV", "Instagram")))  # fmt: skip


def test_a_person_is_not_read_where_the_template_takes_no_person(conn):
    text = 'Item 1 has a contact "Marc Garage" with the number of PETROV.'
    with pytest.raises(Reject, match="matches no account"):
        filler(conn)._resolve(claim(text), "", proposal(
            "contact_entry", people=[], quoted_text="Marc Garage", phones=["Item 1"],
            accounts=[{"as_written": "PETROV", "app": "Phone"}]))  # fmt: skip


def test_the_display_name_of_one_account_finds_it(conn):
    text = f'On March 18, 2026, Marcus R wrote "{QUOTE}" on Telegram.'
    out = filler(conn)._resolve(claim(text), "", proposal(
        "sender", **sender("Marcus R", "Telegram")))  # fmt: skip
    # the same account, seen on both phones: one identifier
    assert out.params["account_ids"] == ["acct:item1:Telegram:7001002",
                                         "acct:item2:Telegram:7001002"]  # fmt: skip


def test_a_display_name_on_an_app_the_claim_does_not_name_is_refused(conn):
    text = f'On March 18, 2026, Marcus R wrote "{QUOTE}".'
    with pytest.raises(Reject, match="matches no account"):
        filler(conn)._resolve(claim(text), "", proposal("sender", **sender("Marcus R", "Telegram")))


def _extra(conn, aid: str, ident: str, name: str) -> None:
    conn.execute(
        "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier,"
        " display_name) VALUES (?, 'src:none', ?, NULL, 'Telegram', ?, ?)",
        (aid, f"extra/{aid}", ident, name),
    )


def test_a_display_name_two_accounts_carry_is_refused(conn):
    _extra(conn, "acct:extra:1", "7009999", "Marcus R")
    try:
        text = f'On March 18, 2026, Marcus R wrote "{QUOTE}" on Telegram.'
        with pytest.raises(Reject, match="is the name of 2 Telegram accounts"):
            filler(conn)._resolve(claim(text), "", proposal(
                "sender", **sender("Marcus R", "Telegram")))  # fmt: skip
    finally:
        conn.execute("DELETE FROM accounts WHERE id = 'acct:extra:1'")


def test_a_person_and_an_account_of_someone_else_with_the_same_name_is_refused(conn):
    _extra(conn, "acct:extra:2", "7008888", "PETROV")
    try:
        text = f'On March 18, 2026, PETROV wrote "{QUOTE}" on Telegram.'
        with pytest.raises(Reject, match="not confirmed as theirs"):
            filler(conn)._resolve(claim(text), "", proposal(
                "sender", **sender("PETROV", "Telegram")))  # fmt: skip
    finally:
        conn.execute("DELETE FROM accounts WHERE id = 'acct:extra:2'")


def test_a_person_whose_name_two_other_accounts_carry_is_refused_as_not_theirs(conn):
    # The reason names the real problem, not the two accounts' shared name.
    _extra(conn, "acct:extra:3", "7007777", "PETROV")
    _extra(conn, "acct:extra:4", "7006666", "PETROV")
    try:
        text = f'On March 18, 2026, PETROV wrote "{QUOTE}" on Telegram.'
        with pytest.raises(Reject, match="not confirmed as theirs"):
            filler(conn)._resolve(claim(text), "", proposal(
                "sender", **sender("PETROV", "Telegram")))  # fmt: skip
    finally:
        conn.execute("DELETE FROM accounts WHERE id IN ('acct:extra:3', 'acct:extra:4')")


def test_a_person_written_as_an_account_is_one_more_party(conn):
    # Beside a writer, the person is a second party. A sender takes one party, so the
    # template refuses; it never reads as "sent by PETROV or REYES".
    # (Written as the one it went to, REYES is refused before that: test_assumption_filler.)
    text = f'On March 18, 2026, PETROV and REYES wrote "{QUOTE}" on Instagram.'
    p = proposal(
        "sender", people=["PETROV"], accounts=[{"as_written": "REYES", "app": "Instagram"}]
    )
    out = filler(conn)._resolve(claim(text), "", p)
    assert out.params["person_ids"] == [PETROV, REYES]
    with pytest.raises(ValueError, match="name exactly one party"):
        parse_params("sender", out.params)
    # where the template takes two parties, the meaning is kept: no contact between the two
    text = "On March 18, 2026, PETROV had no contact with REYES on Instagram."
    p = proposal("no_contact", quoted_text="", people=["PETROV"],
                 accounts=[{"as_written": "REYES", "app": "Instagram"}],
                 window={"as_written": "On March 18, 2026", "start": "2026-03-18T00:00",
                         "end": "2026-03-19T00:00", "zone": "phone"})  # fmt: skip
    out = filler(conn)._resolve(claim(text, ClaimType.ABSENCE), "", p)
    assert out.params["person_ids"] == [PETROV, REYES]
    assert out.params["channels"] == ["Instagram"]
    assert not parse_params("no_contact", out.params).account_ids


def test_an_apps_name_written_as_an_account_is_refused(conn):
    text = f'On March 18, 2026, PETROV wrote "{QUOTE}" on Telegram.'
    with pytest.raises(Reject, match="matches no account"):
        filler(conn)._resolve(claim(text), "", proposal(
            "sender", **sender("Telegram", "Telegram")))  # fmt: skip


def test_an_at_handle_still_goes_to_the_checks(conn):
    # "@alex92" is a display name too; written with "@" it stays a handle, as before.
    text = f'On March 18, 2026, @alex92 wrote "{QUOTE}" on Telegram.'
    out = filler(conn)._resolve(
        claim(text), "", proposal("sender", **sender("@alex92", "Telegram"))
    )
    assert (out.params.get("handles"), out.params.get("account_ids")) == (["@alex92"], None)
