## 2026-10-20: Windows installer signed with Artifact Signing (#106)
- Changed: Arsh set up Microsoft Artifact Signing (Basic account `bakersigning`, individual
  identity validation, Public Trust profile `bakerpublic`, app `baker-github-signing` with a
  federated credential for main and the Certificate Profile Signer role, 2 GitHub secrets and 3
  variables). Builds of main now ship a signed `Baker-Setup-<version>.exe`, so Windows names the
  publisher instead of "Unknown publisher". `windows-installer.yml` now fails a build of main
  whose signing settings are missing, and its smoke test fails an unsigned main build, instead of
  shipping an unsigned file with a warning (PRs and other branches still build unsigned).
  `PILOT_ONBOARDING.md` step 3, `SECURITY_PRIVACY.md` and `packaging/windows/README.md` now say
  the installer is signed, and `speedtest.ps1` prints the signer instead of "unsigned until...".
  `docs/code-signing.md` now lists the steps the real setup needed: register
  `Microsoft.CodeSigning`, self-assign Identity Verifier, pick Individual, use an "Other issuer"
  federated credential with GitHub's ID-based subject (the GitHub scenario's subject fails with
  AADSTS70025), and search the app by name for the Signer role (missing role: 403). Pilot gate 10
  is met.
- Where: main (#106, merged 2026-10-20)
- Verified: windows-installer run 39496196827 on main `e8b373a` (GitHub windows-latest,
  2026-10-20): signed by `CN=Shayan Haque`, `Get-AuthenticodeSignature` Valid; smoke-test job
  installed the signed file on a fresh runner, case01 model-free gate PASS (accuracy 1.00, 0 false
  supported), browser smoke test passed, uninstall clean. Two earlier attempts of the same run
  failed at login (no federated credential) and at signing (403, no role) before the fixes.
- Open: SmartScreen reputation for the new signature is unmeasured; no one has run the signed
  installer on a real Windows PC yet. The uninstaller is still unsigned (by design, #55). The
  certificate is in an individual's name until a company exists; Artifact Signing costs about
  $9.99/month (Microsoft's price, unverified by us).
- Affects: customer-facing claims (the Windows installer is now signed). No capability, privacy,
  network or performance change in Baker itself.
- Status doc: applied 2026-10-21
