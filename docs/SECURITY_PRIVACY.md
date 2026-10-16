# Security and privacy

For firms, examiners and counsel deciding whether to install Baker. As of 2026-10-15, `main`
`19d8461` (after #68 and #74 merged).

**Baker is local by default; cloud AI only when your case allows it and you opt in.** The opt-in
cloud option (#68) is in the code, but it is gated on a model passing Baker's signed stance test,
and **no model has** (`PROBE_PASSED` in `core/llm/cloud.py` is empty). So today every case labels
locally and nothing from a case leaves the computer. Statements about what an opted-in case would
send are marked "opted-in case".

## 1. Data flow

```
 Expert's computer (everything happens here today)
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                                                                             │
 │  Original files ──read-only, SHA-256──▶ Case folder                          │
 │  (government PDF,                       ├─ inputs/   copies (AES-256-GCM     │
 │   Cellebrite / AXIOM                    │            if the case is encrypted)│
 │   reports)                              ├─ case.db   records, claims, labels,│
 │   never modified                        │            decisions, audit log    │
 │                                         │            (SQLCipher if encrypted)│
 │                                         ├─ case.key  case key, wrapped       │
 │                                         └─ case.json case name etc. (plain)  │
 │                                                ▲                             │
 │  Local model (Qwen3-14B, pinned SHA-256) ◀──────┤ claims, assumptions,       │
 │                                                 │ stance labels, AI review   │
 │  Browser ◀── http://127.0.0.1 only ──▶ Baker screen                          │
 │                                                 │                            │
 │  Report (plain HTML) ◀── saved only when the expert downloads it             │
 │                                                                             │
 └───────────────────────────────┬─────────────────────────────────────────────┘
                                 │ Opted-in case only (none can be today: no
                                 │ model has passed the gate): one stance question
                                 │ per (assumption, record) pair, sent up to 3
                                 │ times on a network error, timeout, 408, 409,
                                 │ 429 or 5xx; each send logged first
                                 ▼
                     api.anthropic.com (Claude, the expert's own key)
```

| Data | Every case today | Opted-in case, once a model passes the gate |
|---|---|---|
| Original evidence files | Stay on the computer, never modified | Same. Never sent |
| Case database (all records, claims, decisions, audit log) | Stays on the computer | Same. Never sent |
| Claim proposal, assumption filling, optional AI review | Local model | Local model |
| Stance labels (does this record support, contradict or complicate this assumption?) | Local model | Claude Opus 5.5. Each request holds the filled-in stance prompt: the assumption, one record, its nearby messages, the claim text and, for a group chat, the member list. A send that fails on a network error, timeout, 408, 409, 429 or 5xx is sent again, up to 3 sends in all, each logged before it goes |
| Report | Written only where the expert saves it | Same |
| Telemetry, analytics, crash reports, accounts, license server | None | None |

Install-time downloads, before any case exists:

- **Model file (both platforms):** checked against its pinned SHA-256 before use; a file with any
  other hash is refused.
- **Windows:** Python and Baker's packages ship inside the installer, so Setup itself downloads
  only the optional model. The installer is built in CI: the embedded Python and the model runtime's
  source are pinned by SHA-256 (`packaging/windows/pins.json`); the CUDA toolkit is pinned by
  version only, and Baker's other Python packages come from PyPI without hash pinning. Check the installer's own SHA-256 before
  running it.
- **Mac:** the installer runs uv's install script from astral.sh, lets uv fetch Python 3.12, and
  installs Baker's Python packages and the model runtime (`llama-cpp-python`, version pinned) from
  the package index. **These are not hash-pinned**: they trust astral.sh, the Python download
  source and PyPI over HTTPS. A firm that needs more can read `packaging/mac/install.sh` before running it, or wait
  for a signed Mac package (not built yet). Copying an installed `~/Baker` folder to another Mac is
  not supported: the environment and launchers hold paths from the computer that installed it.

An offline computer can take the model from a USB drive.

## 2. Encryption at rest

Full design: `docs/encryption.md`.

- **What is encrypted.** `case.db` with SQLCipher 4 (AES-256 per page, HMAC-SHA512 per page) and
  every file in `inputs/` with AES-256-GCM in authenticated 1 MiB chunks.
- **Default.** New cases made in the browser are encrypted by default (the box can be unticked).
  `baker init` on the command line and the synthetic demo make plain cases. An existing plain case
  is never encrypted silently; the expert presses "Encrypt this case" or runs `baker encrypt`.
- **Not encrypted.** `case.json`, so a locked case can be listed. It holds the case name, when the
  case was made, who made it (the name entered on the screen), the claim order (claim ids only) and
  the timeline tolerance and gap settings. Don't put a client's name in the case name if that
  matters. Also not encrypted: downloaded reports, and anything on screen while a case is unlocked.
- **Hashes** are of the plain bytes, so a file's SHA-256 matches the original whether or not the
  case is encrypted.
- Use the computer's own disk encryption too (FileVault, BitLocker). Python cannot guarantee memory
  is wiped, and an SSD can keep old blocks of a case that was encrypted after it was made.

## 3. Key handling

- **Case key.** Each case has its own random 256-bit key. It is never stored in the clear:
  `case.key` holds it wrapped with AES-256-GCM twice, once under a key derived from the expert's
  passphrase (scrypt) and once under a recovery key shown once, when the case is encrypted.
- **Unlocked key.** Lives only in the memory of the running Baker. Stopping Baker or pressing
  "Lock this case now" locks the case. The OS keychain is not used.
- **Passphrase entry.** The command line asks for it in the terminal. It is never read from an
  option or an environment variable, so it stays out of shell history.
- **Lost both passphrase and recovery key.** Nobody can open the case, Baker included.
- **Cloud API key (opted-in case).** The expert's own Anthropic key; Baker runs no server and holds no key of
  its own. It is read from `$BAKER_ANTHROPIC_API_KEY`; or, in an encrypted case, from the key saved
  in that case, sealed with AES-256-GCM under the case key, so it is unreadable while the case is
  locked; or from `~/.baker/cloud.json`, an owner-only (0600) plain file. The key travels in a
  request header and is never written to the audit log.

## 4. Retention and deletion

**On the computer.** Baker deletes nothing on a schedule. A case is kept until the expert deletes
it. Baker has no "delete case" button: delete the case folder (under `~/Baker/cases` by default),
plus any backups of it, any downloaded reports, any request draft downloaded from the case
(`baker-request-draft.txt`: file names, device labels, extraction details, hashes) and any
`baker ufdr-check` output folder (`ufdr-check-private.md` holds sample records). Outside the case folders Baker writes only small
settings under `~/.baker`: `model.json` (which model file to use), `model-check.json` (the model
file's checked hash), `speed.json` (seconds per model call) and, if the expert saves an Anthropic key outside a case,
`cloud.json`. None holds case content; `cloud.json` holds the key. Each case folder also has
`case.db.anchors.jsonl`, unencrypted, beside `case.db` (audit-log entry numbers and hashes, no case content).

For an encrypted case, first lock it ("Lock this case now") or stop Baker, because a running Baker
keeps an unlocked case's key in memory. Then destroy `case.key` and every copy of the recovery key,
and check that the case no longer opens. The data is then unreadable. The old plain files of a case encrypted after it was made may remain in free SSD blocks;
disk encryption covers that.

**At Anthropic (opted-in case only).** Requests go to the Claude API under the expert's own account, so
Anthropic's terms for that account apply, not Baker's. Read them rather than our summary:

- [How long Anthropic stores an organization's data](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)
- [API and data retention, including zero data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention)
- [Commercial Terms](https://www.anthropic.com/legal/commercial-terms)

Checked 2026-10-15 on the API retention page: under a zero data retention (ZDR) arrangement
Anthropic does not store prompts or responses at rest after the response is returned; ZDR is
requested per organization from Anthropic, so Baker cannot turn it on; and if a request is flagged
by Anthropic's trust and safety systems, inputs and outputs may be kept for up to 2 years. The
Commercial Terms say Anthropic may not train models on customer content from its services. Check
the current pages before relying on any of this.

## 5. Cloud policy

A case uses cloud stance labels only when **all** of these hold, and otherwise runs fully local:

1. The expert attests, for this case, that "This case's protective order (or the court or the
   government's consent) allows its evidence to be sent to a cloud AI service under my firm's
   account, and my client has given informed consent to it." The attestation, who made it and when
   go into the case's hash-chained audit log.
2. The case is **not** marked as possibly containing child sexual abuse material. Such material
   stays in the government's control (18 U.S.C. 3509(m)), so a marked case never uses cloud,
   whatever the attestation says.
3. The expert's own Anthropic key is set up.
4. The model passed Baker's signed stance test with the current prompt. **No model has.** Opus 5.5
   scored 73% contradicts precision against a 90% bar on 2026-10-15, so every case labels locally
   until a signed prompt fix passes and Arsh signs a gate entry for that model, effort and prompt.

Further rules for an opted-in case:

- **No mixed labels.** In an opted-in case every stance label comes from the cloud. If the cloud
  fails, the audit pauses; the expert retries, or turns cloud off and the whole case runs locally.
- **Logged before sent.** Each request body is written to the case's audit log (`cloud.sent`)
  before it is sent. If that entry can't be written, nothing is sent.
- **Pinned endpoint.** Only `https://api.anthropic.com`; a stray `ANTHROPIC_BASE_URL` cannot
  redirect case data.
- **Same checks.** A cloud answer must be valid JSON and its quote must pass the verbatim check,
  exactly like a local answer. Cloud labels never set verdicts.

Whether cloud AI may be used is a decision for the case's protective order and counsel. This
document is not legal advice.

## 6. How to verify the network claim

**Read the tests.** These run on every CI push, on Ubuntu and Windows:

| Test | What it checks |
|---|---|
| `tests/test_govdoc.py::test_core_makes_no_network_imports` | No file in `core/` imports `socket`, `ssl`, `urllib`, `http`, `requests`, `httpx`, `aiohttp`, `ftplib` or `smtplib` |
| `tests/test_llm_runtime.py::test_core_llm_has_no_network_imports` | No file in `core/` imports `requests`, `httpx`, `urllib`, `socket` or `huggingface_hub`, and only `core/llm/cloud.py` may import `anthropic` |
| `tests/test_cloud.py::test_only_the_cloud_file_in_core_imports_a_network_client` | `core/llm/cloud.py` is the only file in `core/` that imports the Anthropic client |
| `tests/test_review_screen.py::test_screen_code_imports_no_network_client` | The screen and report code import no network client |
| `tests/test_review_screen.py::test_the_whole_flow_makes_no_network_call` | A full review, re-decide and report download with every socket connect and DNS lookup made to fail: none is attempted |
| `tests/test_review_screen.py::test_server_binds_loopback_only_and_answers` | The screen binds 127.0.0.1 only |
| `tests/test_packaging.py::test_no_network_tool_ships_in_core` | The only download in the Windows installer is the optional model step |

Run them yourself from a source checkout (7 passed on 2026-10-15, Linux, main `19d8461` plus #82):

```
python -m pytest -q \
  tests/test_govdoc.py::test_core_makes_no_network_imports \
  tests/test_llm_runtime.py::test_core_llm_has_no_network_imports \
  tests/test_cloud.py::test_only_the_cloud_file_in_core_imports_a_network_client \
  tests/test_review_screen.py::test_screen_code_imports_no_network_client \
  tests/test_review_screen.py::test_the_whole_flow_makes_no_network_call \
  tests/test_review_screen.py::test_server_binds_loopback_only_and_answers \
  tests/test_packaging.py::test_no_network_tool_ships_in_core
```

**Watch the computer.** The tests check Baker's own code, not the inside of the libraries it uses
(the model runtime, PDF and OCR libraries). To check everything, observe the running program:

1. Turn off Wi-Fi and unplug the network, then run the demo and a synthetic audit. Both work
   offline.
2. Or, with the network on, list Baker's connections while an audit runs. Mac:
   `lsof -i -n -P | grep -i python`. Windows (PowerShell): `Get-NetTCPConnection | Where-Object
   OwningProcess -in (Get-Process python).Id`. The only entries should be the screen listening on
   `127.0.0.1:8765` (8766 for the demo) and your browser's connections to it.
3. A firewall that asks per connection (for example Little Snitch on a Mac) shows the same.

`baker serve --open` asks the operating system to open your browser at the local address; that is
the browser's connection to 127.0.0.1, not an outside one.

Once a model passes the gate, an opted-in case would add HTTPS connections to `api.anthropic.com`, and only those; each
appears in the case's audit log as `cloud.sent`.

## 7. Other safeguards

- Inputs are opened read-only and SHA-256 hashed on import. In the browser workflow, a mismatch
  between the uploaded copy's hash and the bytes parsed is refused with an error and the copy is
  deleted. Known bug in this version: records already parsed from the changed copy can stay in the
  case database (reported for a fix). If you ever see that error, start a new case.
- The local model file is checked against its pinned SHA-256 before loading.
- The screen accepts requests only from the same computer and loads nothing from outside: no
  scripts, no CDN.
- Every examiner action is written to a hash-chained audit log, anchored in a file beside the
  database; the log is checked on open and before every report, and a failure blocks the case. The
  report prints the result and the last hash (see `docs/METHODS.md` for what the chain does and doesn't detect).
- The Windows installer is **not code-signed yet**. Check its SHA-256 before running it
  (`docs/install.md`).
