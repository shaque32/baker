# Signing the Windows installer

Builds of `main` sign `Mabillon-Setup-<version>.exe` with Microsoft Artifact Signing (formerly
Trusted Signing), so Windows names the publisher (Shayan Haque, since 2026-10-20) instead of
"Unknown publisher". A build of main whose signing settings below are missing fails rather than
ship an unsigned file. Pull requests and other branches build unsigned, with the warning
"Installer not signed".

## How the build signs

- Only builds of `main` sign (a push to main, or **Run workflow** on main). Pull requests and
  other branches always build unsigned, so an unreviewed change never carries Mabillon's signature.
- GitHub logs in to Azure with a short-lived token (OIDC). No Azure password or key is stored in
  GitHub, and nothing secret is printed in the logs.
- After signing, the build checks the signature is valid, then writes the `.sha256` of the file
  as shipped. The fresh-runner install test checks both again before installing.
- The setup program is signed. The uninstaller Setup writes is not; Windows does not show a
  publisher warning when Mabillon is removed from Settings.

## Setup (about 20 minutes, after Microsoft finishes the identity check)

First, in Microsoft's Artifact Signing quickstart order (done for Mabillon 2026-10-19/20):

- On the subscription (Pay-As-You-Go, billing account type **Individual** for a person, as on your
  ID): **Settings** > **Resource providers** > register `Microsoft.CodeSigning`.
- Create the Artifact Signing account (Basic tier, East US). Mabillon's is `bakersigning`.
- In that account's **Access control (IAM)**, give yourself the role **Artifact Signing Identity
  Verifier**. Without it, **New identity validation** stays greyed out even for the owner.
- **Identity validations** > **New** > **Public**, then pick **Individual** (the form that opens
  first asks for a company and a DUNS number). Individuals must be in the US or Canada. Finish the
  email and ID check from Microsoft's link. Mabillon's took under a day.
- **Certificate profiles** > **Create** > **Public Trust**, named `bakerpublic`, on that validation.

Then:

1. **App registration.** In <https://portal.azure.com> open **Microsoft Entra ID** > **App
   registrations** > **New registration**. Name `baker-github-signing`, single tenant,
   no redirect URI > **Register**. Copy the **Application (client) ID** and the **Directory
   (tenant) ID** from its overview page.
2. **Trust GitHub's main branch.** In that app: **Certificates & secrets** > **Federated
   credentials** > **Add credential** > scenario **Other issuer** (not "GitHub Actions deploying
   Azure resources": that form writes the old subject `repo:shaque32/baker:ref:refs/heads/main`,
   and this repository's tokens carry the newer one with owner and repository IDs, so login fails
   with AADSTS70025). Issuer `https://token.actions.githubusercontent.com`, type **Explicit
   subject identifier**, value `repo:shaque32@196110499/baker@1407810293:ref:refs/heads/main`,
   audience `api://AzureADTokenExchange`, name `baker-main` > **Add**. The value is the
   "subject claim" the **Azure login** step prints, if it ever changes. (No client secret: leave
   that tab alone.)
3. **Let the app sign.** Open your Artifact Signing account > **Access control (IAM)** > **Add
   role assignment** > role **Artifact Signing Certificate Profile Signer** (older screens:
   Trusted Signing Certificate Profile Signer) > **Select members** > type
   `baker-github-signing` (apps appear only when searched by name) > **Review + assign**.
   Without this role, login works but signing fails with `403 (Forbidden)`.
4. **GitHub secrets.** In <https://github.com/shaque32/baker> > **Settings** > **Secrets and
   variables** > **Actions** > **Secrets** tab > **New repository secret**, twice:
   `AZURE_CLIENT_ID` (the client ID from step 1) and `AZURE_TENANT_ID` (the tenant ID).
5. **GitHub variables.** Same page, **Variables** tab > **New repository variable**, three times:

   | Name | Value |
   |---|---|
   | `ARTIFACT_SIGNING_ENDPOINT` | the account's region endpoint, e.g. `https://eus.codesigning.azure.net/` for East US (the account's overview page shows its URI) |
   | `ARTIFACT_SIGNING_ACCOUNT` | the account name, e.g. `bakersigning` |
   | `ARTIFACT_SIGNING_PROFILE` | the certificate profile name, e.g. `bakerpublic` |

6. **Check it.** **Actions** > **windows-installer** > **Run workflow** on `main`. When it
   finishes, the run's summary says `signed by CN=<your validated name>`. On a Windows PC,
   right-click the installer > **Properties** > **Digital Signatures** shows the same name.

A new signature still gets a SmartScreen warning at first; it fades as people download
installers signed with the same identity. If signing fails after setup, the run stops with the
reason instead of shipping an unsigned file from main.
