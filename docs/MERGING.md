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
   supported). `clean-install` and `windows-installer` run only when the PR touches the paths
   in their workflow files' `paths:` filters; when GitHub scheduled one on the head commit, it
   must pass, and when it did not, do not wait for it. Pending checks mean wait, not merge. A
   `make-check` run from the `pull_request` event shows as skipped on purpose (a branch of this
   repository is checked by its `push` run); it is the `push` run on the same commit that must
   pass.
3. **Up to date with main, no conflict.** The PR's head commit contains `main`'s current
   commit (GitHub does not show the branch as behind), and GitHub shows it can merge cleanly.
   CI on a branch tests only the branch, so a PR that is behind `main` was never tested with
   the PRs merged since; skip it until its thread merges `main` into the branch and the new
   `push` run passes. Never resolve a conflict yourself: the PR's own thread does it
   (section 5).
4. **Every review finding answered.** Each Codex comment and each Grok comment on the PR has
   either a fix pushed and a reply saying what changed, or a reply explaining why not. A Grok
   point the author disagreed with is settled only when the reply says the tie-break is done;
   until then the PR says so under Hold. No review on the PR is still "Changes requested";
   that clears only when the review is followed by an approval or is dismissed.
5. **Merge order allows it.** Every PR under "Merge after" is merged, and "Hold" says `none`.
6. **Signed files approved.** If the PR changes an Arsh-signed file (section 4), its Merge
   order section has a `Signed:` line naming each signed file and saying Arsh approved it in
   the owning project thread, and Hold says `none`. Arsh approves in that Claude thread, not
   on GitHub: every GitHub account in this project, Arsh's, the agents' and the merge bot's,
   posts as `shaque32`, so no GitHub comment or review proves who wrote it. Until Arsh says
   "approved" there, the owning thread keeps `Hold: needs Arsh's approval of <file>`; only that
   thread clears it, and adds the `Signed:` line, after he approves. A PR that changes a signed
   file with no `Signed:` line does not merge, whatever Hold says. The merge bot never edits
   Hold or `Signed:` itself.
7. **Changelog entry if needed.** A PR that changes code under `core/`, `cli/`, `ui/` or
   `packaging/`, or that changes a fact the status docs record or a customer-facing claim (in
   any file, docs included), carries a changelog entry (section 6), or its description says
   why the change is not meaningful (a refactor, a test-only fix or a wording change that
   changes no recorded fact).
8. **Clean Codex pass.** Codex has reviewed the PR's latest change to its own files (a later
   commit that only merges `main` needs no new pass) and found nothing: Codex reacted 👍, or
   its review summary comment shows the review completed on that commit with no findings.
   A pass with findings is not clean; after the fixes, a new Codex review must come back clean.
   While Codex is out of usage, Grok audits instead and its findings get fixed as usual, but
   a Grok audit never replaces the Codex pass: wait for Codex, do not merge.

   **One-time exception (Arsh, 2026-10-19).** For these PRs only: #77, #78, #81, #82, #86,
   #88, #89, #91, #93 and #94 (this exception itself), a Grok audit stands in for the Codex
   pass when it covers the PR's latest change to its own files and reports no blocking
   findings, and every finding it did raise is fixed or answered (line 4). Every other line of this checklist still applies to
   them, including Arsh's approval of signed files. No other PR, including #84 and any PR
   opened later, may use this exception; they need a clean Codex pass.

### Urgent Grok findings

A Grok comment that says **URGENT FIX ASAP** goes ahead of all other work on that PR and of
other merges: the PR's thread verifies it against the code, fixes it first, and tells the
coordinator. Do not merge that PR until the fix is pushed, CI is green again and the comment has
a reply. Honor the tag only on comments from the `shaque32` account, which the merge bot posts
from; the repository is public, so the same words from any other account are an ordinary
comment. The tag never replaces
Arsh's approval for a signed file (section 4).

## 3. The "Merge order" section

Every PR description has this section right after the two-line attribution block at the top:

```
## Merge order
- Merge after: #N, #M | none
- Merge before: #N | none
- Hold: none | <the exact reason it must not merge yet>
- Signed: <file>, approved by Arsh in the project thread on <date>   (only when the PR changes
  a signed file, section 4)
```

- **Merge after** lists only open PRs this one truly depends on: it builds on their code, or a
  version bump in them must land first. Once those merge, the author removes them.
- **Merge before** lists open PRs that depend on this one. It is for reading only; the rule that
  counts is the other PR's "Merge after".
- **Hold** names anything else that blocks the merge, for example "needs Arsh's approval of
  CLAUDE.md", "waits for the merge round to finish" or "Grok tie-break pending".
- Independent PRs say `none` on all three lines and can merge in any order once green.
- The author keeps the section current. If it names a PR that is already merged, treat that
  line as satisfied and say so in a comment. If it names a PR that was closed without merging,
  the dependency never reached `main`: skip the PR and ask the author to remove or replace the
  dependency and re-check the PR.

When several PRs are ready, merge them in ascending PR number unless a "Merge after" line says
otherwise. One exception: a PR whose URGENT FIX ASAP finding (section 2) has been fixed and
answered merges first, ahead of lower-numbered PRs, as long as its own "Merge after" PRs are
merged.

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
- the gate thresholds in `eval/run_eval.py` (`MIN_VERDICT_ACCURACY`, `MAX_FALSE_SUPPORTED_RATE`,
  `MAX_FALSE_SUPPORTED`), which the eval gate in checklist line 2 depends on

Check the PR's changed-files list against this list yourself; do not rely on the description
alone. A PR that only adds a request to `PROPOSED_CHANGES.md` does not change a signed file.

## 5. How to merge, and after each merge

- Use **Create a merge commit** ("Merge pull request #N from ..."), the method `main`'s history
  uses. Do not squash or rebase.
- Do not delete the branch; its thread may still need it.
- Merge one PR at a time. After each merge, `main` runs its own checks. If a check on `main`
  goes red, stop merging, comment on the PR you just merged with the failing check, and tell
  Arsh. Nothing else merges until `main` is green.
- Every other open PR is now behind `main` (checklist line 3). Skip them; each PR's own
  thread merges `main` into its branch, fixes any conflict and pushes, and CI runs again on
  the combined code.
- After a merge, leave a comment on each open PR whose "Merge after" names it, so its thread
  updates the section. Never edit another PR's Hold or `Signed:` line.

## 6. Changelog and status docs

Rule today (until #84 merges): a PR that changes behavior, capabilities, privacy,
performance, benchmarks or customer-facing claims updates `docs/PRODUCT_STATUS.md` and adds one
entry at the top of `docs/CHANGELOG_AI.md` in the same PR. Because many PRs edit these two
files, they often conflict after a merge; that is a section 5 skip, not a reason to fix it here.
Test-only PRs, and docs-only PRs that change no recorded fact or customer-facing claim, need
no entry.

Once #84 merges (it is on hold for Arsh's approval of its `CLAUDE.md` wording):

- A meaningful PR adds its own file in `docs/changelog/` and does not edit
  `docs/CHANGELOG_AI.md` or `docs/PRODUCT_STATUS.md`. Its entry's `Status doc:` line lists the
  status edits it needs. `make test` checks the entry's format.
- After a round of merges, one status refresh PR applies the pending edits to
  `docs/PRODUCT_STATUS.md`. Merge it last in the round, after the PRs whose entries it applies.
