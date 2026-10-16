# Merging pull requests

The rulebook for whoever merges a pull request into `main`: Arsh, or the merge bot that audits
and merges for him. Every rule here can be checked from the PR page alone (its description,
checks, review comments and files). When a rule cannot be checked, do not merge; say why on the
PR and move on.

## 1. Never merge these

- Draft pull requests.
- #50, #70 and #80. They stay open on purpose.
- Grok review PRs: every PR whose number is a multiple of ten from 70 up (70, 80, 90, 100...).
  They are empty drafts that hold Grok Product's review comments. Never merge or close them.
- A PR whose description has no "Merge order" section (section 3). Ask for one in a comment.

## 2. Merge checklist

Merge a PR only when every line is true. If one is false, skip the PR, say which line failed in
one comment on the PR, and go on to the next PR.

1. **Not excluded.** It is not in section 1.
2. **CI green on the latest commit.** Every check run on the PR's current head commit has
   finished and passed. Required: the `checks` workflow (`make check` on Linux and Windows:
   lint, tests and the eval gate, which needs case01 accuracy of at least 0.80 and zero false
   supported). When a PR touches installer files, `clean-install` and `windows-installer` run
   too and must pass. Pending checks mean wait, not merge.
3. **No conflict with main.** GitHub shows the branch can merge cleanly. Never resolve a
   conflict yourself: the PR's own thread does it (section 5).
4. **Every review finding answered.** Each Codex comment and each Grok comment on the PR has
   either a fix pushed and a reply saying what changed, or a reply explaining why not. A Grok
   point the author disagreed with is settled only when the reply says the tie-break is done;
   until then the PR says so under Hold.
5. **Merge order allows it.** Every PR under "Merge after" is merged, and "Hold" says `none`.
6. **Signed files approved.** If the PR changes an Arsh-signed file (section 4), Arsh has
   approved it: either Arsh commented "approved" on the PR, or the Hold line, which said it
   needed his approval, has been changed to `none` by the PR's author after he approved.
7. **Changelog entry if needed.** A PR that changes code under `core/`, `cli/`, `ui/` or
   `packaging/` carries a changelog entry (section 6), or its description says why the change
   is not meaningful (a refactor, a test-only fix or a wording change).

## 3. The "Merge order" section

Every PR description has this section right after the two-line attribution block at the top:

```
## Merge order
- Merge after: #N, #M | none
- Merge before: #N | none
- Hold: none | <the exact reason it must not merge yet>
```

- **Merge after** lists only open PRs this one truly depends on: it builds on their code, or a
  version bump in them must land first. Once those merge, the author removes them.
- **Merge before** lists open PRs that depend on this one. It is for reading only; the rule that
  counts is the other PR's "Merge after".
- **Hold** names anything else that blocks the merge, for example "needs Arsh's approval of
  CLAUDE.md", "waits for the merge round to finish" or "Grok tie-break pending".
- Independent PRs say `none` on all three lines and can merge in any order once green.
- The author keeps the section current. If it names a PR that is already merged or closed, treat
  that line as satisfied and say so in a comment.

When several PRs are ready, merge them in ascending PR number unless a "Merge after" line says
otherwise.

## 4. Arsh-signed files

A PR that changes any of these needs Arsh's approval before it merges, even with green CI and
every finding answered:

- `CLAUDE.md`
- `core/contracts.py`
- `core/schema.sql`
- `core/audit/rules.py` (verdict rules and `RULE_VERSION`)
- anything under `core/audit/prompts/` (stance, reviewer, claim and assumption prompts)
- anything under `eval/gold/` (gold labels, the signed stance guide and the mock affidavit)
- the `PROBE_PASSED` entries in `core/llm/cloud.py` (they decide whether a cloud model may label
  a case)

Check the PR's changed-files list against this list yourself; do not rely on the description
alone. A PR that only adds a request to `PROPOSED_CHANGES.md` does not change a signed file.

## 5. How to merge, and after each merge

- Use **Create a merge commit** ("Merge pull request #N from ..."), the method `main`'s history
  uses. Do not squash or rebase.
- Do not delete the branch; its thread may still need it.
- Merge one PR at a time. After each merge, `main` runs its own checks. If a check on `main`
  goes red, stop merging, comment on the PR you just merged with the failing check, and tell
  Arsh. Nothing else merges until `main` is green.
- Other open PRs may now conflict with `main`. Skip them; each PR's own thread merges `main`
  into its branch, fixes the conflict and pushes, and CI runs again.
- After a merge, update the "Merge after" and "Hold" lines that named it, or leave a comment
  so the author does.

## 6. Changelog and status docs

Rule today (until #84 merges): a PR that changes behavior, capabilities, privacy,
performance, benchmarks or customer-facing claims updates `docs/PRODUCT_STATUS.md` and adds one
entry at the top of `docs/CHANGELOG_AI.md` in the same PR. Because many PRs edit these two
files, they often conflict after a merge; that is a section 5 skip, not a reason to fix it here.
Docs-only and test-only PRs need no entry.

Once #84 merges (it is on hold for Arsh's approval of its `CLAUDE.md` wording):

- A meaningful PR adds its own file in `docs/changelog/` and does not edit
  `docs/CHANGELOG_AI.md` or `docs/PRODUCT_STATUS.md`. Its entry's `Status doc:` line lists the
  status edits it needs. `make test` checks the entry's format.
- After a round of merges, one status refresh PR applies the pending edits to
  `docs/PRODUCT_STATUS.md`. Merge it last in the round, after the PRs whose entries it applies.
