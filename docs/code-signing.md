# Signing the Windows installer

Until the installer is signed, Windows says "Unknown publisher" and an expert has to check the
SHA-256 and choose **Run anyway** (docs/install.md). The build signs `Baker-Setup-<version>.exe`
with Microsoft Artifact Signing (formerly Trusted Signing) as soon as the settings below exist.
Until then it builds unsigned and the run shows the warning "Installer not signed".

## How the build signs

- Only builds of `main` sign (a push to main, or **Run workflow** on main). Pull requests and
  other branches always build unsigned, so an unreviewed change never carries Baker's signature.
- GitHub logs in to Azure with a short-lived token (OIDC). No Azure password or key is stored in
  GitHub, and nothing secret is printed in the logs.
- After signing, the build checks the signature is valid, then writes the `.sha256` of the file
  as shipped. The fresh-runner install test checks both again before installing.
- The setup program is signed. The uninstaller Setup writes is not; Windows does not show a
  publisher warning when Baker is removed from Settings.

## Setup (about 20 minutes, after Microsoft finishes the identity check)

First create the Artifact Signing account (Basic tier), pass Microsoft's identity validation and
create a **Public Trust** certificate profile, as in Microsoft's Artifact Signing quickstart.
Then:

1. **App registration.** In <https://portal.azure.com> open **Microsoft Entra ID** > **App
   registrations** > **New registration**. Name `baker-github-signing`, single tenant,
   no redirect URI > **Register**. Copy the **Application (client) ID** and the **Directory
   (tenant) ID** from its overview page.
2. **Trust GitHub's main branch.** In that app: **Certificates & secrets** > **Federated
   credentials** > **Add credential** > scenario **GitHub Actions deploying Azure resources**.
   Organization `shaque32`, repository `baker`, entity type **Branch**, branch `main`, name
   `baker-main` > **Add**. (No client secret: leave that tab alone.)
3. **Let the app sign.** Open your Artifact Signing account > **Access control (IAM)** > **Add
   role assignment** > role **Artifact Signing Certificate Profile Signer** (older screens:
   Trusted Signing Certificate Profile Signer) > members: `baker-github-signing` > **Review +
   assign**.
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
