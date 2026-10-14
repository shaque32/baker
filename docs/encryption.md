# Encryption at rest

Baker can lock a case's files on the expert's computer with a passphrase. A copied case folder,
a lost laptop, a backup or a synced folder then holds nothing readable without the passphrase or
the case's recovery key.

## What is encrypted

| In the case folder | Encrypted? | How |
|---|---|---|
| `case.db` (every message, call, claim, finding and the audit log) | Yes | SQLCipher 4: AES-256 per page with an HMAC-SHA512 check per page; its journal too |
| `inputs/` (the copies of the imported reports and government document) | Yes | AES-256-GCM in 1 MiB chunks, each chunk authenticated |
| `case.key` (the case's key, wrapped) | Holds no usable key | AES-256-GCM wraps under scrypt-derived keys |
| `case.json` (the case name, the claim order) | No | So the case list can name a locked case. Do not put a client's name in the case name if that matters |

Not covered: a report or request letter the expert downloads (saved wherever they choose, as a
plain file), the expert's original evidence files (Baker never changes them), and anything on
screen while a case is unlocked.

The SHA-256 Baker records for every imported file is of the plain bytes, so it still matches the
original file and the hash in the report, encrypted or not.

## The passphrase and the recovery key

Each case gets its own random 256-bit key. Baker never stores it in the clear: `case.key` holds
it wrapped twice, once under the expert's passphrase and once under a recovery key that Baker
shows **once**, when the case is encrypted. Either opens the case.

- Write the recovery key down and keep it away from the computer (paper, or a password manager).
- Changing the passphrase re-wraps the key; nothing is re-encrypted, and the recovery key stays
  the same.
- If both the passphrase and the recovery key are lost, nobody can open the case, Baker
  included. The original evidence is untouched; the expert's review work in that case is lost.

An unlocked key lives only in the memory of the running Baker. Stopping Baker (or pressing
"Lock this case now") locks the case. Locking also drops the index of message text the Selection
tab keeps in memory to look quotes up quickly. Python cannot promise to wipe memory, so turn on the
computer's own disk encryption too (FileVault on a Mac, BitLocker on Windows).

## New cases

"New case" on the case list has "Encrypt this case with a passphrase" ticked. Untick it for a
plain case (for example a synthetic test case). `baker demo` cases are synthetic and stay plain.

## Cases made before encryption

Nothing encrypts an existing case on its own: it opens exactly as before, with the same files.
To encrypt one, when no audit is running on it:

- in the browser: open the case, "Set up and run", the **Encryption** section at the bottom,
  enter a passphrase twice, "Encrypt this case"; or
- in a terminal: `baker encrypt --db ~/Baker/cases/<case>/case.db --by "expert:Your Name"`.

Baker refuses while an audit is recorded as running, takes the database's write lock, writes
`case.key`, copies the database into an encrypted file and checks it (integrity, every table's
row count, the audit log's hash chain and last hash), encrypts each copied file and reads it
back against its SHA-256, then swaps the encrypted files in and logs `case.encrypt` in the audit
log. It does not change any finding. A large report can take a few minutes.

If it stops part way (a crash, a full disk), the case still opens; the Encryption section says
"Encryption did not finish", and the same step with the same passphrase finishes it. It then
shows a new recovery key, since the first one may never have reached the screen.

The old plain files are replaced, not wiped. On an SSD their blocks can stay readable to
forensic tools until reused; disk encryption covers that.

## Commands

```
baker encrypt    --db CASE/case.db --by "expert:Your Name"   # encrypt, or finish encrypting
baker passphrase --db CASE/case.db --by "expert:Your Name"   # change the passphrase
```

Every other command on an encrypted case (`audit`, `report`, `verify-log`, ...) asks for the
passphrase or recovery key in the terminal. It is never read from an option or an environment
variable, so it does not end up in shell history.
