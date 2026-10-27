## 2026-10-20: what a cloud request carries, and its open limits
- Changed: docs only. `docs/SECURITY_PRIVACY.md` section 5 now lists exactly what one cloud
  stance request carries (claim text, assumption, the record's full text, up to 20 messages
  either side with device-local times, handles, numbers, saved names and confirmed people, a
  members line of up to 20; never a file, the database, locators, hashes or the case name) and
  what is logged with each answer (`cloud.received`: request id, message id, served model); the
  open limitations (retention at Anthropic not verified by Mabillon; only a key saved into an
  encrypted case is sealed, while the environment variable and the settings file stay plain;
  attestation self-certified; hosted labels cannot be regenerated); and
  recommends local mode where the tool's reliability may be challenged in court.
  `docs/install.md`, `docs/install-mac.md` and `docs/review-screen.md` point to it. Why: legal
  defensibility brief (Arsh, 2026-10-20), PR C; follow-up to #102's caveats.
- Where: main (#133, merged 2026-10-24)
- Verified: each listed field checked against `core/audit/stance.py` `create`,
  `core/audit/prompts/stance_cloud.md`, `core/audit/context.py` (`DEFAULT_WINDOW = 20`,
  `MAX_MEMBERS = 20`), `core/audit/readable.py`, `core/enrich/records.py` and
  `core/llm/cloud.py` `ClaudeModel.request`, and `cloud.received` against
  `core/audit/_local_model.py`, on main `1e641eb` (2026-10-24), and the key order against
  `core/llm/cloud.py` `load_config` and `core/paths.py` on main `e715796`. No code changed.
- Open: Anthropic's retention for a given account is the expert's to check; not legal advice.
- Affects: customer-facing claims (what a cloud request holds; local mode recommended for
  contested cases); privacy (documentation only, no behavior change).
- Status doc: applied 2026-10-27
