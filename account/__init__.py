"""Mabillon sign-in: who holds a license, and nothing else.

Plan: /mnt/project-files/baker/plans/desktop-sign-in.md (2026-11-06). Sign-in stays OFF
(`SIGNIN_ON`) until Arsh signs the privacy wording and a real sign-in works end to end; while it is
off, nothing here runs, nothing connects, and every audit starts as it does today.

- `account.license` checks a signed license on this computer. It imports no network client.
- `account.flow` makes the one-use values a browser sign-in hands back to the app (RFC 8252).
- `account.client` is the only file outside `core/llm/cloud.py` that connects to anything, and
  only to `account.getmabillon.com`. It never sends anything from a case.

A license only controls starting a new audit. Opening Mabillon, opening a case, review, the
report and export always work, signed in or not.
"""

from __future__ import annotations

# Off until the wording in docs/SECURITY_PRIVACY.md is signed and turned on in its own PR.
SIGNIN_ON = False

ACCOUNT_HOST = "account.getmabillon.com"
