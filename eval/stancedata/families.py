"""The item families both stance-data generators draw from. SYNTHETIC, DRAFT until Arsh signs.

A family fixes the gold stance, the probe category and the trap name. Generators choose a family,
then write a record and an assumption that fit its rule; the label comes from the family, never
from the generator's own judgment. LABELING_GUIDE.md explains every family for the signer, and a
test checks the two stay in step.

Conventions follow the signed stance prompt (core/audit/prompts/stance.md v1.0) and the signed
probe set (eval/gold/probe, P001-P088). Families marked `new` describe a case the signed probe set
does not cover; Arsh decides them when he signs the guide. Families marked `disputed` follow a
signed label that the probe set itself marks disputed; they are generated for training, and the
held-out set marks their items disputed so they never count toward a bar.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    new: bool = False  # a convention the signed probe set does not cover yet
    disputed: bool = False  # the signed probe items of this kind are marked disputed


_F = Family

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
       "The record states a fact that cannot hold at the same time as the assumption, such as "
       "being back home against still being abroad."),
    _F("con_in_window", C.CONTRADICTS, S.CONTRADICTS, None, (K.COMPLETENESS, K.TIME),
       "The assumption says there was no contact in a window, or that first contact came on a "
       "date; the record is a message between those accounts inside the window, or earlier."),
    _F("con_other_speaker", C.CONTRADICTS, S.CONTRADICTS, None, (K.IDENTITY, K.EVENT),
       "In a group chat, the assumption attributes words to one member; the record shows a "
       "different member wrote them."),
    # Overreach: looks like support on the surface. Gold is contradicts for these four.
    _F("ovr_time_mismatch", C.OVERREACH, S.CONTRADICTS, "time_mismatch", (K.TIME,),
       "Same words and people, but the record's local date or local clock time falls outside "
       "what the assumption states; at a DST change the local clock reading decides."),
    _F("ovr_sender_mismatch", C.OVERREACH, S.CONTRADICTS, "sender_mismatch", (K.EVENT, K.IDENTITY),
       "The assumption says one account sent the words; the record shows a different account "
       "sent them."),
    _F("ovr_later_correction", C.OVERREACH, S.CONTRADICTS, "later_correction", (K.EVENT,),
       "The record states the assumed fact, but a later message from the same sender in the "
       "context replaces it with an incompatible value."),
    _F("ovr_negation", C.OVERREACH, S.CONTRADICTS, "negation", (K.EVENT,),
       "The assumption's words appear in the record inside a negated statement."),
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
       "The context marks the record as a joke or sarcasm; the assumption takes it literally."),
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
