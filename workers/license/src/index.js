// Mabillon's license server at https://account.getmabillon.com. The app's sign-in opens
// /signin in the system browser; the expert enters a work email; we email a one-time link; the
// link page sends the browser back to the app on http://127.0.0.1:<port>/signin/done with a code;
// the app trades the code and its PKCE verifier at /api/token for a license signed with our
// Ed25519 key (RFC 8252, RFC 7636). The app renews it at /api/renew at most daily.
//
// What reaches us: the email typed here; then from the app only the code and verifier, the
// license id, the sign-in token and the Mabillon version. Never anything from a case. We keep
// licenses, hashed links, codes and tokens (schema.sql). Plan: plans/desktop-sign-in.md.

const LINK_MINUTES = 15;
const CODE_MINUTES = 5;
const RETURN_RE = /^http:\/\/127\.0\.0\.1:(\d{4,5})\/signin\/done$/;
const B64URL_RE = /^[A-Za-z0-9_-]+$/;
const EMAIL_RE = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;
const VERSION_RE = /^[0-9A-Za-z.+-]{1,40}$/;
const LICENSE_ID_RE = /^lic_[A-Za-z0-9]{8,40}$/;

const CSP =
  "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' http://127.0.0.1:*; " +
  "frame-ancestors 'none'; base-uri 'none'";
const HEADERS = {
  "Content-Security-Policy": CSP,
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Cache-Control": "no-store",
};

// -- small helpers

const enc = new TextEncoder();

function b64url(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(n = 32) {
  return b64url(crypto.getRandomValues(new Uint8Array(n)));
}

export async function sha256(text) {
  return b64url(new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(text))));
}

export function escape(text) {
  return String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

const iso = (d) => d.toISOString();
const later = (now, minutes) => new Date(now.getTime() + minutes * 60000);

export function validReturn(value) {
  const m = RETURN_RE.exec(value || "");
  if (!m) return false;
  const port = Number(m[1]);
  return port >= 1024 && port <= 65535;
}

function okState(value) {
  return typeof value === "string" && value.length >= 20 && value.length <= 100 && B64URL_RE.test(value);
}

function okChallenge(value) {
  return typeof value === "string" && value.length === 43 && B64URL_RE.test(value);
}

function page(title, body, status = 200) {
  const html =
    "<!doctype html><html lang='en'><head><meta charset='utf-8'>" +
    "<meta name='viewport' content='width=device-width, initial-scale=1'>" +
    `<title>${escape(title)} · Mabillon</title><style>` +
    "body{font:16px/1.5 system-ui,sans-serif;max-width:30rem;margin:12vh auto;padding:0 16px;" +
    "color:#1d1d1f;background:#fbfaf7}h1{font-size:1.4rem}input,button{font:inherit;" +
    "padding:.5rem .75rem}input{width:100%;box-sizing:border-box;margin:.25rem 0 1rem}" +
    "button{background:#1d1d1f;color:#fff;border:0;border-radius:6px;cursor:pointer}" +
    ".muted{color:#6e6e73;font-size:.9rem}</style></head><body>" +
    `<h1>${escape(title)}</h1>${body}</body></html>`;
  return new Response(html, {
    status,
    headers: { ...HEADERS, "Content-Type": "text/html; charset=utf-8" },
  });
}

function json(body, status = 200) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { ...HEADERS, "Content-Type": "application/json" },
  });
}

const refuse = (status, error, message) => json({ error, message }, status);

const START_AGAIN = "<p>Start again from Mabillon: open the Account page and press Sign in.</p>";

// -- the signed license

export async function signingKey(env) {
  const jwk = JSON.parse(env.SIGNING_KEY_JWK);
  return crypto.subtle.importKey("jwk", jwk, { name: "Ed25519" }, false, ["sign"]);
}

export async function signLicense(env, lic, now) {
  const text = JSON.stringify({
    v: 1,
    aud: "mabillon",
    kid: env.KEY_ID,
    id: lic.id,
    email: lic.email,
    plan: lic.plan,
    issued_at: iso(now),
    expires: lic.paid_through,
    offline: false,
  });
  const key = await signingKey(env);
  const sig = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, key, enc.encode(text)));
  return { license: text, signature: b64url(sig) };
}

function current(lic, now) {
  return lic && lic.status === "active" && new Date(lic.paid_through) > now;
}

// -- email

export function linkEmail(link, minutes) {
  return [
    "Here is your link to sign in to Mabillon:",
    "",
    link,
    "",
    `It works once, for ${minutes} minutes. If you did not ask to sign in, ignore this email.`,
    "",
    "Mabillon never sends us anything from your cases.",
  ].join("\n");
}

async function sendLink(env, to, link) {
  const resp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${env.RESEND_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: env.FROM,
      to: [to],
      subject: "Sign in to Mabillon",
      text: linkEmail(link, LINK_MINUTES),
    }),
  });
  if (!resp.ok) throw new Error(`email not sent (${resp.status})`);
}

// -- the pages

function signinForm(q) {
  return page(
    "Sign in to Mabillon",
    "<form method='post' action='/signin'>" +
      `<input type='hidden' name='state' value='${escape(q.state)}'>` +
      `<input type='hidden' name='challenge' value='${escape(q.challenge)}'>` +
      `<input type='hidden' name='return' value='${escape(q.return)}'>` +
      "<label for='email'>Work email</label>" +
      "<input id='email' name='email' type='email' autocomplete='email' required maxlength='200'>" +
      "<button type='submit'>Email me a sign-in link</button></form>" +
      "<p class='muted'>Signing in tells us who holds a license, and nothing else. Mabillon " +
      "never sends us anything from your cases.</p>",
  );
}

function checked(q) {
  return okState(q.state) && okChallenge(q.challenge) && validReturn(q.return);
}

async function startSignin(request, env, now) {
  const form = await request.formData();
  const q = {
    state: form.get("state"),
    challenge: form.get("challenge"),
    return: form.get("return"),
  };
  if (!checked(q)) return page("This sign-in did not come from Mabillon", START_AGAIN, 400);
  const email = String(form.get("email") || "").trim().toLowerCase();
  if (!EMAIL_RE.test(email) || email.length > 200) {
    return page("Enter your work email", "<p>That address does not look right.</p>" + START_AGAIN, 400);
  }
  if (env.LIMITER) {
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const { success } = await env.LIMITER.limit({ key: `${ip}:${email}` });
    if (!success) return page("Please wait a minute", "<p>Too many tries. Wait a minute.</p>", 429);
  }
  const lic = await env.DB.prepare("SELECT * FROM licenses WHERE email = ?").bind(email).first();
  if (current(lic, now)) {
    const token = randomToken();
    await env.DB.prepare(
      "INSERT INTO links (hash, license_id, state, challenge, return_to, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
    )
      .bind(await sha256(token), lic.id, q.state, q.challenge, q.return, iso(later(now, LINK_MINUTES)))
      .run();
    await sendLink(env, email, `${env.ORIGIN}/signin/link?t=${token}`);
  }
  // The same answer either way, so this page never says which addresses hold a license.
  return page(
    "Check your email",
    `<p>If ${escape(email)} holds a Mabillon license, we sent it a sign-in link. It works ` +
      `once, for ${LINK_MINUTES} minutes.</p><p class='muted'>Nothing arrived? Check spam, or ` +
      "write to support@getmabillon.com.</p>",
  );
}

async function liveLink(env, token, now) {
  if (!token || token.length > 100 || !B64URL_RE.test(token)) return null;
  const row = await env.DB.prepare("SELECT * FROM links WHERE hash = ?").bind(await sha256(token)).first();
  if (!row || row.used || new Date(row.expires_at) <= now) return null;
  return row;
}

// GET shows a button, and only the POST uses the link up: mail scanners that open links
// before the expert does cannot spend it.
async function linkPage(url, env, now) {
  const token = url.searchParams.get("t");
  if (!(await liveLink(env, token, now))) {
    return page("This link has expired or was already used", START_AGAIN, 400);
  }
  return page(
    "Sign in to Mabillon",
    "<form method='post' action='/signin/link'>" +
      `<input type='hidden' name='t' value='${escape(token)}'>` +
      "<button type='submit'>Continue to Mabillon</button></form>",
  );
}

async function useLink(request, env, now) {
  const form = await request.formData();
  const row = await liveLink(env, String(form.get("t") || ""), now);
  if (!row) return page("This link has expired or was already used", START_AGAIN, 400);
  const spent = await env.DB.prepare("UPDATE links SET used = 1 WHERE hash = ? AND used = 0")
    .bind(row.hash)
    .run();
  if (!spent.meta || spent.meta.changes !== 1) {
    return page("This link has expired or was already used", START_AGAIN, 400);
  }
  if (!validReturn(row.return_to)) return page("This sign-in did not come from Mabillon", START_AGAIN, 400);
  const code = randomToken();
  await env.DB.prepare("INSERT INTO codes (hash, license_id, challenge, expires_at) VALUES (?, ?, ?, ?)")
    .bind(await sha256(code), row.license_id, row.challenge, iso(later(now, CODE_MINUTES)))
    .run();
  const back = `${row.return_to}?code=${encodeURIComponent(code)}&state=${encodeURIComponent(row.state)}`;
  return new Response(null, { status: 303, headers: { ...HEADERS, Location: back } });
}

// -- the app's API

async function body(request) {
  try {
    const b = await request.json();
    return b && typeof b === "object" && !Array.isArray(b) ? b : null;
  } catch {
    return null;
  }
}

async function token(request, env, now) {
  const b = await body(request);
  if (!b || typeof b.code !== "string" || typeof b.verifier !== "string" || !VERSION_RE.test(b.v || "")) {
    return refuse(400, "bad_request", "The request was not understood.");
  }
  if (b.code.length > 100 || b.verifier.length < 43 || b.verifier.length > 128) {
    return refuse(400, "bad_request", "The request was not understood.");
  }
  const hash = await sha256(b.code);
  const row = await env.DB.prepare("SELECT * FROM codes WHERE hash = ?").bind(hash).first();
  if (!row || row.used || new Date(row.expires_at) <= now) {
    return refuse(400, "used", "This sign-in is out of date or was already used. Start again in Mabillon.");
  }
  const spent = await env.DB.prepare("UPDATE codes SET used = 1 WHERE hash = ? AND used = 0").bind(hash).run();
  if (!spent.meta || spent.meta.changes !== 1) {
    return refuse(400, "used", "This sign-in is out of date or was already used. Start again in Mabillon.");
  }
  if ((await sha256(b.verifier)) !== row.challenge) {
    return refuse(400, "mismatch", "This sign-in did not start on this computer. Start again in Mabillon.");
  }
  const lic = await env.DB.prepare("SELECT * FROM licenses WHERE id = ?").bind(row.license_id).first();
  if (!current(lic, now)) return refuse(403, "expired", "This license has ended. Write to support@getmabillon.com.");
  const secret = randomToken();
  await env.DB.prepare(
    "INSERT INTO tokens (hash, license_id, created_at, last_renewed_at, app_version) VALUES (?, ?, ?, ?, ?)",
  )
    .bind(await sha256(secret), lic.id, iso(now), iso(now), b.v)
    .run();
  return json({ ...(await signLicense(env, lic, now)), token: secret });
}

async function signedIn(b, env) {
  if (!b || typeof b.token !== "string" || b.token.length > 200 || !LICENSE_ID_RE.test(b.license_id || "")) {
    return null;
  }
  const hash = await sha256(b.token);
  const row = await env.DB.prepare("SELECT * FROM tokens WHERE hash = ? AND license_id = ?")
    .bind(hash, b.license_id)
    .first();
  return row ? { hash, row } : null;
}

async function renew(request, env, now) {
  const b = await body(request);
  if (!b || !VERSION_RE.test(b.v || "")) return refuse(400, "bad_request", "The request was not understood.");
  const found = await signedIn(b, env);
  if (!found) return refuse(401, "signed_out", "This computer is no longer signed in. Sign in again.");
  const lic = await env.DB.prepare("SELECT * FROM licenses WHERE id = ?").bind(b.license_id).first();
  if (!current(lic, now)) return refuse(403, "expired", "This license has ended. Write to support@getmabillon.com.");
  await env.DB.prepare("UPDATE tokens SET last_renewed_at = ?, app_version = ? WHERE hash = ?")
    .bind(iso(now), b.v, found.hash)
    .run();
  return json(await signLicense(env, lic, now));
}

async function signout(request, env) {
  const found = await signedIn(await body(request), env);
  if (found) await env.DB.prepare("DELETE FROM tokens WHERE hash = ?").bind(found.hash).run();
  return json(null, 204);
}

// -- routing

export async function handle(request, env, now = new Date()) {
  const url = new URL(request.url);
  const route = `${request.method} ${url.pathname}`;
  switch (route) {
    case "GET /signin": {
      const q = Object.fromEntries(url.searchParams);
      if (q.challenge_method !== "S256" || !checked(q)) {
        return page("This sign-in did not come from Mabillon", START_AGAIN, 400);
      }
      return signinForm(q);
    }
    case "POST /signin":
      return startSignin(request, env, now);
    case "GET /signin/link":
      return linkPage(url, env, now);
    case "POST /signin/link":
      return useLink(request, env, now);
    case "POST /api/token":
      return token(request, env, now);
    case "POST /api/renew":
      return renew(request, env, now);
    case "POST /api/signout":
      return signout(request, env);
    default:
      return page("Not found", "<p>There is nothing here.</p>", 404);
  }
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (err) {
      console.error("license server error", err && err.message);
      return page("Something went wrong", "<p>Try again in a minute, or write to support@getmabillon.com.</p>", 500);
    }
  },
};
