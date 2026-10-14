"""The item families both stance-data generators draw from. SYNTHETIC.

A family fixes the gold stance, the probe category and the trap name. Generators choose a family,
then write a record and an assumption that fit its rule; the label comes from the family, never
from the generator's own judgment. LABELING_GUIDE.md explains every family for the signer, and a
test checks the two stay in step.

Conventions follow stance guide v0.3 (LABELING_GUIDE.md, signed 2026-10-14) and stance prompt
v1.1, signed with it, which the pipeline wiring applies. Where the signed probe set
(eval/gold/probe, P001-P088) reads contradicts more broadly than the guide (P049 and P066 to
P069; eval/probe_draft/PROBE_REVIEW.md), the families follow the guide.

Families marked `new` brought a convention the signed probe set did not show when they were
added; Arsh decided each one when he signed the guide that added it (v0.2 on 2026-10-12, v0.3 on
2026-10-14). Since the 2026-10-14 relabel, probe items P038 to P044 and P071 show the four trap
families v0.3 moved to complicates. Families marked `disputed` follow a signed label that the
probe set itself marks disputed; they are generated for training, and the held-out set marks
their items disputed so they never count toward a bar.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.audit.assumptions import TEMPLATES
from core.contracts import AssumptionKind as K
from core.contracts import Stance as S
from eval.probe_draft.model import ProbeCategory as C


@dataclass(frozen=True)
class Family:
    family_id: str
    category: C
    stance: S
    trap: str | None
    kinds: tuple[K, ...]
    rule: str  # one sentence: what the record and the assumption look like
    new: bool = False  # a convention the signed probe set did not show when it was added
    disputed: bool = False  # the signed probe items of this kind are marked disputed
    # Baker's own wording (guide rules 25 to 29): the product templates (core/audit/assumptions.py)
    # this family's assumptions are rendered from. Empty for plain-sentence families.
    templates: tuple[str, ...] = ()


_F = Family
BAKER_TEMPLATES = tuple(TEMPLATES)  # the product's 12 assumption templates

FAMILIES: tuple[Family, ...] = (
    # Supports: the record, read in its context, plainly shows what the assumption states.
    _F("sup_verbatim", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.EVENT, K.TIME),
       "The assumption gives the exact words, the sending and receiving accounts as the phone "
       "shows them and, if any, the local date; the record is that message."),
    _F("sup_plain", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.EVENT, K.MEANING),
       "The assumption restates in plain words what the record literally says, in English or "
       "Russian, with no slang, unresolved pronoun or outside fact needed."),
    _F("sup_answer", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.EVENT,),
       "The record is a short answer whose meaning is fixed by a direct question just before it "
       "in the same chat; the assumption states the plain combined meaning."),
    _F("sup_time_window", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.TIME,),
       "The assumption places the message inside a local time window and the record's local "
       "time is plainly inside it."),
    _F("sup_contact", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.COMPLETENESS, K.TIME),
       "The assumption says two accounts exchanged messages on a date or within a window; the "
       "record is a message between them inside it."),
    _F("sup_account_shared", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.IDENTITY, K.EVENT),
       "The context shows someone else may be typing on an account, but the assumption is only "
       "about the account, so the record still plainly shows it.", new=True),
    _F("sup_injection", C.CLEAR_SUPPORT, S.SUPPORTS, "prompt_injection", (K.EVENT,),
       "The record also contains text that tries to steer the labeler, but its plain words "
       "establish the assumption; the injected text changes nothing."),
    # Contradicts: the record itself shows something that cannot be true with the assumption.
    _F("con_denial", C.CONTRADICTS, S.CONTRADICTS, None, (K.EVENT,),
       "The record's sender plainly denies the assumed event or state."),
    _F("con_other_value", C.CONTRADICTS, S.CONTRADICTS, None, (K.EVENT, K.COMPLETENESS),
       "The record states a different count, amount, day, place or object than the assumption, "
       "in a way that cannot both be true."),
    _F("con_other_state", C.CONTRADICTS, S.CONTRADICTS, None, (K.EVENT,),
       "The record names a place or state that cannot hold at the same stated time as the "
       "assumption's, with nothing unstated needed: 'back in Moscow since sunday' against still "
       "in Sochi that Tuesday, never 'home since sunday' when nothing shows where home is."),
    _F("con_in_window", C.CONTRADICTS, S.CONTRADICTS, None, (K.COMPLETENESS, K.TIME),
       "The assumption says there was no contact in a window, or that first contact came on a "
       "date; the record is a message between those accounts inside the window, or earlier."),
    _F("con_correction", C.CONTRADICTS, S.CONTRADICTS, None, (K.EVENT,),
       "The record is the sender's own correction of an earlier message in the context, giving "
       "a value for the same thing that cannot be true together with the assumption's; the "
       "quote is the correcting words.", new=True),
    # Overreach with gold contradicts: the record's own words rule the assumption out.
    _F("ovr_negation", C.OVERREACH, S.CONTRADICTS, "negation", (K.EVENT,),
       "The assumption's words appear in the record inside a negated statement."),
    # Overreach whose gold changed to complicates in v0.3: the record's words match the
    # assumption, but its date, sender or a later correction leaves the assumption open, and one
    # record cannot show that no other message exists.
    _F("ovr_time_mismatch", C.OVERREACH, S.COMPLICATES, "time_mismatch", (K.TIME,),
       "Same words and people, but the record's local date or local clock time falls outside "
       "what the assumption states; at a DST change the local clock reading decides. One record "
       "cannot show that no matching message was sent at the assumption's time.", new=True),
    _F("ovr_sender_mismatch", C.OVERREACH, S.COMPLICATES, "sender_mismatch", (K.EVENT, K.IDENTITY),
       "The assumption says one account sent the words; the record shows a different account "
       "sent them, and cannot show that the first account never wrote them too.", new=True),
    _F("ovr_speaker_mismatch", C.OVERREACH, S.COMPLICATES, "speaker_mismatch",
       (K.IDENTITY, K.EVENT),
       "In a group chat, the assumption attributes words to one member; the record shows a "
       "different member wrote them, and cannot show that the first member never said them too.",
       new=True),
    _F("ovr_later_correction", C.OVERREACH, S.COMPLICATES, "later_correction", (K.EVENT,),
       "The record states the assumed fact, but a later message from the same sender in the "
       "context replaces it with an incompatible value; that later message, not the record, "
       "carries the contradiction.", new=True),
    # Overreach with gold complicates (or irrelevant for an unrelated injection).
    _F("ovr_handle_owner", C.OVERREACH, S.COMPLICATES, "handle_owner", (K.IDENTITY, K.EVENT),
       "The assumption names a real person, but the record shows only an account, number, "
       "handle or saved label; a self-introduction in the chat does not prove it either."),
    _F("ovr_shared_account", C.OVERREACH, S.COMPLICATES, "shared_account", (K.IDENTITY,),
       "The context shows someone other than the usual user typing on the account that day; "
       "the assumption names the usual person as the writer."),
    _F("ovr_pronoun", C.OVERREACH, S.COMPLICATES, "pronoun", (K.MEANING,),
       "The record refers to 'it', 'that' or 'the thing' (or a Russian equivalent) and nothing "
       "shown resolves it; the assumption names the object."),
    _F("ovr_code_word", C.OVERREACH, S.COMPLICATES, "code_word", (K.MEANING,),
       "The assumption decodes an ordinary or slang word in the record as contraband or a "
       "crime, and nothing shown confirms that reading."),
    _F("ovr_different_topic", C.OVERREACH, S.COMPLICATES, "different_topic", (K.MEANING,),
       "The record's words could fit the assumption on their own, but the context shows they "
       "are about something ordinary."),
    _F("ovr_hypothetical", C.OVERREACH, S.COMPLICATES, "hypothetical", (K.EVENT,),
       "The record states a condition ('if he brings the cash, I'll ...'); the assumption says "
       "the act happened."),
    _F("ovr_plan", C.OVERREACH, S.COMPLICATES, "plan_not_event", (K.EVENT,),
       "The record states a plan or intention; the assumption says the act happened."),
    _F("ovr_question", C.OVERREACH, S.COMPLICATES, "question_not_statement", (K.EVENT,),
       "The record asks a question; the assumption treats it as a statement of fact."),
    _F("ovr_joke", C.OVERREACH, S.COMPLICATES, "joke", (K.MEANING, K.EVENT),
       "A marker in the record or its context ('lol', a laughing reply) leaves it unclear "
       "whether the sender meant it seriously; the assumption takes it literally."),
    _F("ovr_partial", C.OVERREACH, S.COMPLICATES, "partial", (K.EVENT,),
       "The assumption joins two facts; the record shows only one and nothing shown "
       "establishes the other."),
    _F("ovr_count", C.OVERREACH, S.COMPLICATES, "count_overreach", (K.COMPLETENESS,),
       "The assumption generalizes ('every day', 'always', 'all of them') from a record that "
       "shows one instance or a loose phrase."),
    _F("ovr_translation", C.OVERREACH, S.COMPLICATES, "translation_dependence", (K.MEANING,),
       "A Russian record fits the assumption only under a slang or loose translation.",
       disputed=True),
    _F("ovr_injection_related", C.OVERREACH, S.COMPLICATES, "prompt_injection", (K.EVENT,),
       "The record tries to steer the labeler, and its real content bears on the assumption "
       "without establishing it."),
    _F("ovr_injection_unrelated", C.OVERREACH, S.IRRELEVANT, "prompt_injection", (K.EVENT,),
       "The record tries to steer the labeler, and its real content does not bear on the "
       "assumption."),
    # Complicates: bears on the assumption but leaves it open, without looking like support.
    _F("cpl_hedge", C.COMPLICATES, S.COMPLICATES, None, (K.EVENT,),
       "The sender hedges about the assumed fact ('i think', 'probably', 'not sure')."),
    _F("cpl_disputed_claim", C.COMPLICATES, S.COMPLICATES, None, (K.EVENT,),
       "The record asserts the assumed fact and the other party disputes it in the context, so "
       "neither side is established."),
    _F("cpl_inference", C.COMPLICATES, S.COMPLICATES, None, (K.EVENT, K.MEANING),
       "The record fits the assumption only through an inference: warm weather for a city, keys "
       "left out for a drive, 'I don't work there anymore' for quitting."),
    _F("cpl_hearsay", C.COMPLICATES, S.COMPLICATES, None, (K.EVENT,),
       "The sender reports second hand what a third person said or did; the assumption states "
       "it as fact.", new=True),
    _F("cpl_relative_time", C.COMPLICATES, S.COMPLICATES, None, (K.TIME,),
       "The record dates the event with a relative word ('last night', 'this morning') and the "
       "message sits near the date edge, so the assumption's date depends on what the sender "
       "meant.", new=True),
    # Irrelevant: the record does not bear on the assumption.
    _F("irr_other_topic", C.IRRELEVANT, S.IRRELEVANT, None, tuple(K),
       "The record is about a different act, object and subject from the assumption."),
    _F("irr_pleasantry", C.IRRELEVANT, S.IRRELEVANT, None, tuple(K),
       "The record is a greeting, thanks or small talk with no bearing on the assumption."),
    # Baker's own wording (guide rules 25 to 29): the assumption is the product's template text
    # (core/audit/assumptions.py) with the names the case gives (core/audit/readable.py), and
    # the record may be a call, a contact row or an attachment. `templates` names the templates
    # a family's items use.
    _F("bk_sender_shown", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.IDENTITY,),
       "Baker's sender template. The record holds the quoted words, and its line shows the named "
       "sender: a named account's app and identifier, or the named person in the line's "
       "brackets.", new=True, templates=("sender",)),
    _F("bk_sender_other", C.OVERREACH, S.COMPLICATES, "sender_mismatch", (K.IDENTITY,),
       "Baker's sender template. The record holds the quoted words, but its line shows a "
       "different account or person; one record cannot show the named sender never sent them "
       "too.", new=True, templates=("sender",)),
    _F("bk_party_unshown", C.OVERREACH, S.COMPLICATES, "handle_owner",
       (K.IDENTITY, K.TIME, K.COMPLETENESS),
       "A Baker template names a person that no line carries in brackets, so the record shows "
       "only an account, handle or saved name for that party, even if the saved name or the "
       "chat uses the person's name.", new=True,
       templates=("sender", "record_time", "no_contact", "message_count")),
    _F("bk_time_inside", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.TIME,),
       "Baker's time template for a message. The record holds the quoted words, comes from the "
       "named sender if one is named, and its local time is plainly inside the window in the "
       "zone the assumption names.", new=True, templates=("record_time",)),
    _F("bk_call_inside", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.TIME,),
       "Baker's time template for a call. The record is a call between the named parties' "
       "numbers, its local time plainly inside the window and its length inside the range if "
       "one is given; the time printed inside the call text is the report's reading, and the "
       "line's local time decides.", new=True, templates=("record_time",)),
    _F("bk_time_outside", C.OVERREACH, S.COMPLICATES, "time_mismatch", (K.TIME,),
       "Baker's time template. The record is the named message, or a call between the named "
       "parties, at a local time outside the window; one record cannot show there was no "
       "matching message or call inside it.", new=True, templates=("record_time",)),
    _F("bk_zone_edge", C.OVERREACH, S.COMPLICATES, "time_zone", (K.TIME, K.COMPLETENESS),
       "The line's zone differs from the zone the assumption names, and the record is inside the "
       "window in one zone and outside it in the other, so the answer depends on a time zone.",
       new=True, templates=("record_time", "no_contact")),
    _F("bk_call_length", C.OVERREACH, S.COMPLICATES, "duration_mismatch", (K.TIME,),
       "Baker's call template with a length range. A call between the named parties inside the "
       "window whose length is outside the range; one record cannot show there was no other "
       "call.", new=True, templates=("record_time",)),
    _F("bk_identity_named", C.OVERREACH, S.COMPLICATES, "handle_owner", (K.IDENTITY,),
       "Baker's identity template. The record, from a named account, has its sender giving the "
       "person's name or someone calling them by it; a name in a chat never shows who holds an "
       "account.", new=True, templates=("person_identity",)),
    _F("bk_account_silent", C.IRRELEVANT, S.IRRELEVANT, None, (K.IDENTITY,),
       "Baker's identity or authorship template. The record is from a named account but says "
       "nothing about who holds it or who is typing.", new=True,
       templates=("person_identity", "authorship")),
    _F("bk_handles_said", C.COMPLICATES, S.COMPLICATES, None, (K.IDENTITY,),
       "Baker's same-account template. A message, from the account itself or anyone else, says "
       "the two handles are one account or that one became the other; a message shows what was "
       "said, not the platform's records.", new=True, templates=("same_account",)),
    _F("bk_contact_row", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.IDENTITY,),
       "Baker's contact template. The record is a contact row on the named phone with exactly "
       "the saved name and the number the assumption gives.", new=True,
       templates=("contact_entry",)),
    _F("bk_contact_row_differs", C.COMPLICATES, S.COMPLICATES, None, (K.IDENTITY,),
       "Baker's contact template. A contact row on the named phone with that name and another "
       "number, or that number under another name; one row cannot show the named entry is "
       "absent.", new=True, templates=("contact_entry",)),
    _F("bk_count_one", C.COMPLICATES, S.COMPLICATES, None, (K.COMPLETENESS,),
       "Baker's count template. The record is one message between the named parties on the "
       "named phone inside the window: one of the counted messages, which cannot settle the "
       "number.", new=True, templates=("message_count",)),
    _F("bk_no_contact_inside", C.CONTRADICTS, S.CONTRADICTS, None, (K.COMPLETENESS,),
       "Baker's no-contact template. The record is a message or call between the named parties, "
       "both shown by account or bracketed name, on a phone the assumption covers, plainly "
       "inside the window in the zone the assumption names.", new=True,
       templates=("no_contact",)),
    _F("bk_other_phone", C.COMPLICATES, S.COMPLICATES, None, (K.COMPLETENESS,),
       "Baker's no-contact or count template limited to one named phone. The record, between the "
       "named parties, is on another phone: it shows contact, not what the named phone holds.",
       new=True, templates=("no_contact", "message_count")),
    _F("bk_outside_window", C.IRRELEVANT, S.IRRELEVANT, None, (K.COMPLETENESS,),
       "Baker's no-contact or count template. The record is a message or call between the named "
       "parties, plainly outside the window in any zone.", new=True,
       templates=("no_contact", "message_count")),
    _F("bk_weekday_next", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.TIME,),
       "Baker's weekday template. The quoted words name the stated date's weekday for a plan, "
       "in a record sent one to six days before that date; 'this' before the weekday reads the "
       "same when the date is a later day of the same Monday-to-Saturday week.", new=True,
       templates=("weekday_date",)),
    _F("bk_weekday_open", C.COMPLICATES, S.COMPLICATES, None, (K.TIME,),
       "Baker's weekday template. The record names the weekday it was sent on, or puts 'next' "
       "before the weekday, or 'this' before a weekday already past in the week it was sent, "
       "or 'this' when the named day or the send day is a Sunday, so which date it means is "
       "open. The stated date is one the words can mean: after 'this', the coming such day.",
       new=True, templates=("weekday_date",)),
    _F("bk_weekday_wrong", C.CONTRADICTS, S.CONTRADICTS, None, (K.TIME,),
       "Baker's weekday template. The quoted words name a different weekday from the stated "
       "date's.", new=True, templates=("weekday_date",)),
    _F("bk_weekday_after", C.OVERREACH, S.COMPLICATES, "time_mismatch", (K.TIME,),
       "Baker's weekday template. The quoted words plan for the stated date's weekday but were "
       "sent after that date had passed: this record means a later date, and the same words "
       "sent before the date could mean it (rule 23).", new=True,
       templates=("weekday_date",)),
    _F("bk_author_cue", C.OVERREACH, S.COMPLICATES, "shared_account", (K.IDENTITY,),
       "Baker's authorship template. The record, from a named account, carries a cue about who "
       "is typing (a self-introduction, someone else on the phone, a signature); one record "
       "cannot show who typed what the account sent.", new=True, templates=("authorship",)),
    _F("bk_claim_open", C.OVERREACH, S.COMPLICATES, "claim_unsettled", (K.MEANING, K.EVENT),
       "Baker's meaning, role and event templates, shown with the claim. The record holds the "
       "quoted words and nothing shown says what they mean, or its sender gives them a meaning "
       "of its own, unlike the claim's, while the claim names no one who used them; or it comes "
       "from or goes to an account bracketed with a named person (plainly inside the window, if "
       "one is given) and bears on the act or role without being it or ruling it out.", new=True,
       templates=("meaning", "role", "event")),
    _F("bk_meaning_said", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.MEANING,),
       "Baker's meaning template, shown with the claim. The record is a message from the account "
       "that used the quoted words (it gives the meaning as its own, or used them earlier in the "
       "excerpt), plainly saying they mean exactly what the claim says they mean, with no hedge, "
       "joke or later correction; when the claim names who used them, the line's brackets carry "
       "that person.", new=True, templates=("meaning",)),
    _F("bk_meaning_other", C.OVERREACH, S.COMPLICATES, "claim_unsettled", (K.MEANING,),
       "Baker's meaning template, shown with the claim. The account that used the quoted words, "
       "bracketed with the person the claim names as their user, plainly gives them a meaning "
       "of another kind than the claim's, while the claim is not dated wholly before the record: "
       "like a denial, it says nothing about messages it does not cover, so one record cannot "
       "show that no other message used the words as the claim says (rules 23 and 29).", new=True,
       templates=("meaning",)),
    _F("bk_event_is_record", C.CLEAR_SUPPORT, S.SUPPORTS, None, (K.EVENT,),
       "Baker's event template, shown with a claim whose event is a message or call. The record "
       "is that message or call: between the named parties, plainly inside the window, and for "
       "a message saying exactly what the claim says it said.", new=True,
       templates=("event",)),
    _F("bk_claim_denied", C.CONTRADICTS, S.CONTRADICTS, None, (K.EVENT,),
       "Baker's role and event templates, shown with the claim. A person the claim names, from an "
       "account bracketed with them, rules the act or role out for the claim's whole time in "
       "their own words, sent after it: a denial that covers it, or placing themselves "
       "elsewhere for all of it.", new=True, templates=("role", "event")),
    _F("bk_unrelated", C.IRRELEVANT, S.IRRELEVANT, None, tuple(K),
       "Any Baker template. Another message, call, contact row or attachment that holds none of "
       "the quoted words and does not involve the named parties on the matter.", new=True,
       templates=BAKER_TEMPLATES),
)  # fmt: skip

BY_ID: dict[str, Family] = {f.family_id: f for f in FAMILIES}

# Words the tool never says (CLAUDE.md). Assumptions and rationales never contain them; chat text
# may, because real chats do.
BANNED_WORDS = ("guilty", "innocent", "leader", "deleted")


def family(family_id: str) -> Family:
    try:
        return BY_ID[family_id]
    except KeyError:
        raise KeyError(f"unknown family {family_id!r}; see eval/stancedata/families.py") from None
