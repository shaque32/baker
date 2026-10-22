# Private download links for pilot installers

Pilot installers are not on the website. They sit in a private Cloudflare R2 bucket, and each
pilot examiner gets a link that works for a few days and then stops. `tools/pilot_link.py`
makes the links on your own computer. It uses only Python's standard library.

## One-time setup (Cloudflare dashboard, about 15 minutes)

1. **Turn on R2** (about 3 min). Go to Cloudflare dashboard > R2 Object Storage. If asked, add
   a payment method. The free tier covers 10 GB of storage, and R2 has no fees for
   downloads.
2. **Create the bucket** (about 1 min). Click Create bucket, name it `pilot-installers`, and
   leave location on Automatic. Leave Public access off: the bucket must stay private.
3. **Upload the installers** (about 2 min plus upload time). Open the bucket, click Upload, and
   add the signed Windows installer and the Mac package. Name the files with their version,
   for example `Mabillon-Setup-0.1.0.exe`. The dashboard takes files up to 300 MB. A larger
   file needs `rclone` with a separate key that has Object Read & Write on this bucket only;
   delete that key once the upload is done. Never use the read-only key from step 4 for this.
4. **Create a read-only key** (about 3 min). Go to R2 > Manage R2 API Tokens (API on the R2
   page) > Create API token.
   - Permission: Object Read only.
   - Specify bucket: `pilot-installers` only.
   - TTL: Forever, or a date you will remember to renew.

   Click Create. The next page shows the Access Key ID and the Secret Access Key **once**, so
   copy both now. The Account ID is on the R2 overview page.
5. **Save them on your Mac** (about 2 min). Add these four lines to `~/.zshrc`, then open a new
   Terminal window:

   ```
   export R2_ACCOUNT_ID=<account id>
   export R2_ACCESS_KEY_ID=<access key id>
   export R2_SECRET_ACCESS_KEY=<secret access key>
   export R2_BUCKET=pilot-installers
   ```

   Never put these in the repo, in a message or in a ticket.

## Making a link (under a minute)

```
cd ~/baker
python3 tools/pilot_link.py Mabillon-Setup-0.1.0.exe --check
```

It prints one link and the time it stops working, in UTC. `--check` confirms the file is in
the bucket before making the link. The default is 3 days. Use `--days 7` for the longest link
allowed, or `--hours 12` for a shorter one.

- Anyone who has the link can download the file until it expires, so send it only to the
  pilot examiner.
- Expired links cannot be renewed. Make a new one.
- A link can't be cancelled before it expires. To stop all links at once, delete the API token
  in step 4 (every link made with it stops) and create a new one.
- Send the installer's SHA-256 with the link, so the examiner can check the download.
