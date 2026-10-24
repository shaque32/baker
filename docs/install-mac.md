# Installing Mabillon on a Mac

Mabillon runs on your own Mac, offline by default. Nothing about your cases leaves the computer and
Mabillon sends no telemetry, unless you opt a case in to cloud AI at case setup (only if its
protective order allows it). Then, for that case only, one stance question at a time goes to
Anthropic (Claude Opus 5.5) under your own key (see "Cloud AI for this case" on the setup
screen): the claim, the assumption, the record and up to 20 messages either side, with their
senders' handles, numbers and saved names, never a file or the case database. Its open limits
(retention at Anthropic unverified by Mabillon, a key that is sealed only when saved into an
encrypted case, a self-certified attestation, labels that cannot be regenerated) are in
[SECURITY_PRIVACY.md](SECURITY_PRIVACY.md), section 5. Where the tool's reliability may be
challenged in court, keep the case local. The installer downloads three
things, once: a Python installer (uv), the model runtime's source, and the AI model (9 GB).
After that you can disconnect from the internet, except while a case that uses cloud AI is being
audited.

## What you need

| | Minimum | Recommended |
|---|---|---|
| Mac | Apple silicon (M1 or later) | M3 or M4 |
| Memory | 16 GB (a case runs, slowly) | 24 GB or more |
| Disk | 15 GB free | SSD (every Apple silicon Mac has one) |
| macOS | 13 Ventura or later | the latest |

How long a case takes: the synthetic test case (20 claims) took about 6 to 8 hours on an M4 Mac
with 24 GB on an earlier version (2026-10-12). The current version has not been timed yet. Start a case in the evening and review it the next
morning. A run can stop and resume: finished claims are kept.

## Install (about 30 minutes, most of it waiting)

1. Unzip the Mabillon folder you were sent (or downloaded) into your Downloads folder.
2. Open **Terminal** (press Command and Space, type Terminal, press Return).
3. Type `bash ` (with a space after it), drag the file `packaging/mac/install.sh` from the Mabillon
   folder into the Terminal window, and press Return. Or double-click
   **Install Baker.command** in the same folder; the first time, macOS may make you
   right-click it and choose **Open**.
4. If a window asks to install Apple's command line tools, click **Install**, wait for it to
   finish, then run step 3 again. This happens once.
5. Wait. Building the model runtime takes 5 to 10 minutes, and downloading the model depends on
   your connection. If the download stops, run step 3 again: it picks up where it left off.

When it says **Done**, two icons are on your Desktop:

- **Baker** opens your cases in your browser.
- **Baker demo** opens a ready-made, fully synthetic demo case (see docs/demo.md).

Each opens a Terminal window; closing that window stops Mabillon. Mabillon's address is
`http://127.0.0.1:8765` (8766 for the demo), which only this Mac can open.

## Offline computer

Copy `Qwen3-14B-Q4_K_M.gguf` (from <https://huggingface.co/Qwen/Qwen3-14B-GGUF>, Apache-2.0
license) into `~/Baker/models` from a USB drive, then run the installer with `--no-model`, or
without it: a file already in place is checked, not downloaded again. The model's SHA-256 must
be

    500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0

The installer itself still needs the internet once for Python and the runtime.

## Where things are

| What | Where |
|---|---|
| Mabillon and its Python | `~/Baker/app` |
| The model | `~/Baker/models` |
| Your cases | `~/Mabillon/cases` (each case is one folder) |
| The demo case | `~/Mabillon/demo` |
| The model setting | `~/.baker/model.json` (an existing one is never overwritten) |

## Check the install

Open Terminal and run:

    ~/Baker/app/.venv/bin/baker model-check

It says whether the model is there, is the exact pinned file, and fits in this Mac's memory.

## Update or uninstall

To update, unzip the new Mabillon folder and run the installer again; your cases, the model and
your settings stay. To uninstall, delete `~/Baker/app` and the two Desktop icons. Your cases
and the model stay until you delete `~/Baker` and `~/.baker` yourself.
