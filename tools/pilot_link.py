"""Expiring private download links for pilot installers kept in a Cloudflare R2 bucket.

The bucket stays private. Each link is a presigned S3 GET (AWS Signature Version 4) that works
for anyone holding it until it expires, at most 7 days, and then stops working. Nothing is
uploaded or changed: making a link is local signing only, and `--check` sends one HEAD request.

    export R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=...
    python tools/pilot_link.py Mabillon-Setup-0.1.0.exe            # valid 3 days
    python tools/pilot_link.py Mabillon-0.1.0.dmg --days 7 --check  # longest allowed, checked

Not part of the app: nothing in core/ or ui/ imports it.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MAX_SECONDS = 7 * 24 * 3600  # SigV4's limit for a presigned URL
ENV = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def presign(
    *,
    method: str,
    host: str,
    path: str,
    access_key: str,
    secret_key: str,
    region: str,
    expires: int,
    now: datetime.datetime,
) -> str:
    """A SigV4 presigned URL for `method` on https://host/path, signing only the host header."""
    if not 1 <= expires <= MAX_SECONDS:
        raise ValueError(f"expires must be 1 to {MAX_SECONDS} seconds")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    scope = f"{amz_date[:8]}/{region}/s3/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted(query.items())
    )
    canonical_path = urllib.parse.quote(path, safe="/-_.~")
    canonical = "\n".join(
        [method, canonical_path, canonical_query, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"]
    )
    to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
    )
    key = _hmac(("AWS4" + secret_key).encode(), amz_date[:8])
    for part in (region, "s3", "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f"https://{host}{canonical_path}?{canonical_query}&X-Amz-Signature={signature}"


def r2_link(env: dict[str, str], key: str, expires: int, now: datetime.datetime, method="GET"):
    """A presigned link to `key` in the R2 bucket named by `env` (path-style, region auto)."""
    missing = [name for name in ENV if not env.get(name)]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} first (see docs/pilot-links.md).")
    return presign(
        method=method,
        host=f"{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        path=f"/{env['R2_BUCKET']}/{key.lstrip('/')}",
        access_key=env["R2_ACCESS_KEY_ID"],
        secret_key=env["R2_SECRET_ACCESS_KEY"],
        region="auto",
        expires=expires,
        now=now,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make an expiring download link for a file in R2.")
    ap.add_argument("key", help="the file's name in the bucket, e.g. Mabillon-Setup-0.1.0.exe")
    span = ap.add_mutually_exclusive_group()
    span.add_argument("--days", type=float, help="how long the link works (default 3, max 7)")
    span.add_argument("--hours", type=float, help="how long the link works, in hours")
    ap.add_argument("--check", action="store_true", help="confirm the file is in the bucket")
    args = ap.parse_args(argv)

    if args.hours is not None:
        seconds = round(args.hours * 3600)
    else:
        seconds = round((3 if args.days is None else args.days) * 86400)
    if not 1 <= seconds <= MAX_SECONDS:
        ap.error("a link can last at most 7 days")
    now = datetime.datetime.now(datetime.UTC).replace(microsecond=0)

    if args.check:
        # Always the https URL r2_link builds, never a user-given scheme.
        head = urllib.request.Request(  # noqa: S310
            r2_link(dict(os.environ), args.key, 300, now, method="HEAD"), method="HEAD"
        )
        try:
            with urllib.request.urlopen(head, timeout=20) as r:  # noqa: S310
                size = int(r.headers.get("Content-Length") or 0)
        except urllib.error.HTTPError as e:
            reason = "not in the bucket" if e.code == 404 else f"refused (HTTP {e.code})"
            print(f"{args.key}: {reason}. No link made.", file=sys.stderr)
            return 1
        print(f"Found {args.key} ({size / 1e6:.1f} MB).", file=sys.stderr)

    print(r2_link(dict(os.environ), args.key, seconds, now))
    until = now + datetime.timedelta(seconds=seconds)
    print(f"Works until {until:%Y-%m-%d %H:%M} UTC, for anyone who has it.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
