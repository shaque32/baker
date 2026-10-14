"""The held-out stance test set: the exam Baker's own stance model must pass.

SYNTHETIC. Written separately from the training generator (eval/train), from the labeling guide
only, with its own names, situations, slang and wording. Two splits from different seeds: the
test split (ids H...) is scored only for a go or no-go decision; the dev split (ids D...) is for
iterating. Labels come from eval/stancedata/families.py by construction; this package only
writes chats and assumptions that fit each family's rule.

    python -m eval.heldout.generate --out-dir eval/out/stancedata
"""

# 1.2.0: wording for guide draft v0.3. 1.3.0: a denial's act is dated before the message (rule
# 23), an answer's assumption leaves out what the answer leaves open, no "the account's user",
# no generalization bounded by "that month" or "that week", hearsay in the present tense.
GENERATOR = "eval.heldout 1.3.0"
SOURCE = "heldout_gen"
SEEDS = {"test": 1001, "dev": 2002}
ID_PREFIX = {"test": "H", "dev": "D"}
