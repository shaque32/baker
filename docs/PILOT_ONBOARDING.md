# Pilot onboarding

For a defense forensic examiner trying Mabillon for the first time. Follow it top to bottom: install,
run the synthetic demo, then open your first case. Mabillon is alpha software and is **not yet
pilot-ready for real case data** (`docs/PILOT_GATES.md`). Until it is, use the demo and synthetic
cases only, unless the Mabillon team has told you in writing that your pilot has started.

Mabillon is local by default; cloud AI only when your case allows it and you opt in. The case setup
page has a cloud option: for that case only, Claude Opus 5.5 labels the stance questions, under
your own Anthropic key, after you attest that the case's protective order allows it. A case you
mark as possibly containing CSAM never uses cloud AI. Every other step, and every case you do
not opt in, runs on your computer; a cloud case needs internet while it runs.

## 1. Check your computer (5 minutes)

| | Mac | Windows |
|---|---|---|
| Computer | Apple silicon (M1 or later); M3 or M4 recommended | Windows 10 or 11, 64-bit, x64 processor with AVX2 |
| Memory | 16 GB minimum, 24 GB or more recommended | 16 GB minimum, 32 GB recommended |
| Graphics | built in | An NVIDIA card with 12 GB or more is strongly recommended (estimate, not measured) |
| Disk | 15 GB for Mabillon and the model (9 GB), plus about twice the size of your case files | Same, SSD |
| Internet | Once, during install; and while a case you opted in to cloud AI is audited | Once, during install, or none (put the model next to the installer); and while a case you opted in to cloud AI is audited |

How long a case takes is **not yet measured on the current version**. Older measurements on a
24 GB M4 Mac were 22 to 56 seconds per model call, which put the 20-claim synthetic case at
several hours. A 4-core Windows PC without an NVIDIA card was far too slow for real cases. Plan to
run a case overnight. A run can stop and resume; finished claims are kept.

Turn on your computer's disk encryption first (FileVault on a Mac, BitLocker on Windows).

## 2. Install

**Mac (about 30 minutes, mostly waiting).** Full guide: `docs/install-mac.md`.

1. Unzip the Mabillon folder you were sent into Downloads.
2. In the Mabillon folder, open `packaging`, then `mac`, and double-click **Install Baker.command**.
   The first time, macOS may make you right-click it and choose **Open**. (Or open Terminal, type
   `bash ` with a space, drag `packaging/mac/install.sh` into the window and press Return.) If asked to install Apple's command line tools, click **Install**, then
   run the installer again.
3. Wait for **Done**. Two icons appear on your Desktop: **Baker** and **Baker demo**.
4. Check it: in Terminal, run `~/Baker/app/.venv/bin/baker model-check`. It says whether the model
   is present, is the exact pinned file and fits in memory.

**Windows.** Full guide: `docs/install.md`.

1. Get `Baker-Setup-<version>.exe`, and get its SHA-256 value **by a different route** from the
   installer: for example, read it back with the Mabillon team by phone. A `.sha256` file that came
   in the same email, download or shared folder proves nothing, since whoever could swap the
   installer could swap that file too.
2. In PowerShell, run `Get-FileHash .\Baker-Setup-<version>.exe -Algorithm SHA256` and compare it
   with that value. Stop if they differ.
3. Check the publisher: right-click the installer > **Properties** > **Digital Signatures**
   must show **Shayan Haque**. Stop if it shows another name or no signature. Then run it. A new
   signature can still get a SmartScreen warning at first; choose **More info**, then **Run
   anyway**, only after the hash and the publisher both matched.
4. Leave **Download the AI model** ticked. For an offline computer, untick it and put
   `Qwen3-14B-Q4_K_M.gguf` in the same folder as the installer **before** running it; Setup
   checks its SHA-256 and copies it. If you add the model later, put it next to the installer and
   run Setup again (`docs/install.md`).
5. Check it: open **Baker command prompt** from the Start menu and run `mabillon model-check`.

## 3. First run: the demo (15 minutes)

The demo is a ready-made, fully synthetic case (two phones, seven planted traps). No model runs,
so it opens in seconds. Run it before you open anything real.

1. Start it. Mac: double-click **Baker demo**. Windows: in **Baker command prompt**, run
   `mabillon demo`. Your browser opens `http://127.0.0.1:8766`. Only your computer can open that
   address. Closing the window that started it stops Mabillon.
2. Open the case. The setup page lists three imported files, each with its SHA-256, and the phone
   reports marked "curated report", which means they cannot show that something did not happen.
3. Open claim **C05** ("need 2 more by friday"). The model-side label says "supports", but the
   verdict is **Unproven**: nothing is supported until you accept its evidence.
4. Enter your name, type a short reason, click **Accept** on both items, then **Re-run verdicts**.
   C05 becomes "Supported (expert-confirmed)", with your name in the audit log.
5. Open two contradicted claims (C10 and C04 are good ones) and read "Why (reasons from the verdict
   rules)" and the Checks table.
6. Open the **Report**. Look for the source hashes, the rule version, the model runs and the
   audit-log result.

`docs/demo.md` has the answer key for every planted trap. Running `mabillon demo` again resets the
demo to a clean copy.

## 4. Your first case

1. Start Mabillon (Mac: **Baker** on the Desktop; Windows: `mabillon serve --open`). It opens
   `http://127.0.0.1:8765`.
2. **New case.** Leave **Encrypt this case with a passphrase** ticked. Mabillon shows a recovery key
   **once**: write it down and keep it away from the computer. If you lose both the passphrase and
   the recovery key, nobody can open the case, Mabillon included (`docs/encryption.md`).
3. **Set up and run**, in order:
   1. **Files.** Upload the government document (PDF) and the phone reports. Each is copied into
      the case, hashed and made read-only. Your originals are never touched. Check every source's
      coverage line and record count.
   2. **Claims.** Let the local model propose claims, then accept, edit or remove each one, and add
      your own.
   3. **Who used each phone.** Stipulate each device's user, or tick that you accept inconclusive
      sender checks.
   4. **The model.** Click **Check the model**.
   5. **Run the audit.** It runs in the background and keeps the computer awake. Claims appear for
      review as each one finishes.
4. **Review.** For each claim, accept or dismiss the evidence, then confirm or override the
   verdict. Each decision goes into the hash-chained audit log under your name, with an
   override's note. The reason you type for an evidence decision is stored with that decision but
   is not itself covered by the chain.
5. **Report.** Download it from the case. The downloaded report is a plain, unencrypted file:
   store it as you would any case work product.

## 5. When an import is unverified

Mabillon's Cellebrite UFDR and Magnet AXIOM readers were built from documentation and synthetic
samples and have **not been checked on a real export**. The screen and the report mark those
sources "unverified".

1. Read the source's coverage block on the setup page. Anything under "needs review" lists records
   Mabillon skipped or values it could not read, with the location in the report.
2. For a UFDR, run `mabillon ufdr-check --package <file.ufdr> --out <new empty folder>`. It compares
   Mabillon's import with the UFDR's own `report.xml`, offline, and adds nothing to any case. It
   writes `ufdr-check.md` and `ufdr-check.json` (counts and differences, no message text, names
   or numbers), which you may send us after reading them, and `ufdr-check-private.md` (sample
   records to compare in Cellebrite Reader), which is case content and never leaves your computer
   (`docs/ingest/ufdr_check.md`).
3. Compare the record counts per app with what Cellebrite Reader or AXIOM shows for the same
   extraction.
4. Until the counts match, confirm any finding that rests on that source in the original tool
   before you rely on it.
5. Forwarded or quoted messages fail closed: Mabillon warns on them and never lets them support or
   contradict a claim, but their sender field still shows the forwarder and the original text is
   not imported. Check authorship and content of any forwarded message in the
   original tool.

Tell the Mabillon team about every mismatch. It is the most useful thing a pilot can send us.

## 6. When a case is blocked

Every review decision is written to a hash-chained audit log inside the case, and the newest entry's number
and hash are also kept in `case.db.anchors.jsonl` beside the database. If an entry was changed, or
entries were cut from the end back to the newest anchor, the check fails. Entries added after the
newest anchor and cut again before the next check are not caught, and neither is the database
changed together with the anchor file. Keep the last hash from each report you deliver.

Mabillon checks the log when a case opens, on every page while it is open, and before every report.
A failed check shows **Review blocked** on the Cases page with the reason, closes the case (an
encrypted case locks), and refuses any change or report. `mabillon verify-log --db <case
folder>/case.db` says why. `docs/review-screen.md` ("When a case is blocked") has the same steps.

What to do:

1. Stop working in that case. Don't try to repair the database.
2. Stop Mabillon (close the window that started it) and wait for it to exit, so an audit running in
   the background cannot write mid-copy. Then copy the whole case folder as it is, for
   examination.
3. If you have a backup of the case folder from before the problem, restore it to a new folder and
   check it with `mabillon verify-log`.
4. Otherwise start a new case from your original files and repeat your review. To show they are
   the same files, compare their SHA-256 values with a report you delivered or saved **before** the
   problem, or another record kept outside the case. A match with the broken case's own report is
   only a consistency check, since that case's database may have been changed.
5. Tell the Mabillon team what happened, with the `verify-log` output.

Mabillon does not make backups for you. After each review session, wait until no audit is running,
stop Mabillon (close the window that started it), then copy the whole case folder. A copy taken while
Mabillon is writing may not restore. An encrypted case stays encrypted in the copy.

A case can also refuse to open because it is **locked**: enter its passphrase or recovery key. A
case that says **Encryption did not finish** finishes when you repeat the encryption step with the
same passphrase.

## 7. Getting help

Write down what you did, what you saw and the case's rule version (from the report). Never send
case content, screenshots of evidence or the case database. Send the `verify-log` output, or `ufdr-check.md` and
`ufdr-check.json`, and a description instead. Never send `ufdr-check-private.md`: it holds
sample records and is case content.

## Not covered yet

- No one outside the project has completed this kit on a clean Mac without help (pilot gate 11).
- The runtime on the current version is not measured (pilot gate 9).
