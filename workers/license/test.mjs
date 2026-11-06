// Run with: node workers/license/test.mjs  (Node 22 or later, no dependencies)
// The whole sign-in against a real SQLite database standing in for D1 (node:sqlite) and a
// fake email sender. Nothing connects.
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { handle, sha256, validReturn, escape, linkEmail } from "./src/index.js";

const here = fileURLToPath(new URL(".", import.meta.url));

// D1's prepare().bind().first() / run() on node:sqlite
function d1(db) {
  return {
    prepare(sql) {
      let args = [];
      const stmt = {
        bind: (...a) => ((args = a), stmt),
        first: async () => db.prepare(sql).get(...args) ?? null,
        run: async () => {
          const r = db.prepare(sql).run(...args);
          return { meta: { changes: Number(r.changes) } };
        },
      };
      return stmt;
    },
  };
}

const db = new DatabaseSync(":memory:");
db.exec(readFileSync(`${here}schema.sql`, "utf8"));
const keys = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const env = {
  DB: d1(db),
  KEY_ID: "k1",
  SIGNING_KEY_JWK: JSON.stringify(await crypto.subtle.exportKey("jwk", keys.privateKey)),
  RESEND_KEY: "re_test",
  FROM: "Mabillon <signin@getmabillon.com>",
  ORIGIN: "https://account.getmabillon.com",
};
const ORIGIN = env.ORIGIN;
const emails = [];
globalThis.fetch = async (url, init) => {
  assert.equal(url, "https://api.resend.com/emails");
  emails.push(JSON.parse(init.body));
  return new Response("{}", { status: 200 });
};

db.prepare("INSERT INTO licenses (id, email, plan, paid_through, created_at) VALUES (?, ?, ?, ?, ?)").run(
  "lic_abcdefgh1234",
  "expert@lab.example",
  "pilot",
  "2027-11-06T00:00:00.000Z",
  "2026-11-06T00:00:00.000Z",
);

const NOW = new Date("2026-11-06T12:00:00Z");
const minutes = (m) => new Date(NOW.getTime() + m * 60000);
const b64url = (bytes) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function pkce() {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  return { verifier, challenge: await sha256(verifier) };
}

const PORT = 8765;
const RETURN = `http://127.0.0.1:${PORT}/signin/done`;
const STATE = "s".repeat(43);

const req = (method, path, body, headers = {}) => new Request(`${ORIGIN}${path}`, { method, body, headers });
const form = (o) => new URLSearchParams(o);
const api = (path, o) => req("POST", path, JSON.stringify(o), { "Content-Type": "application/json" });
const text = async (r) => await r.text();

// The return address must be this computer's Mabillon screen and nothing else.
assert.ok(validReturn(RETURN));
for (const bad of [
  "http://127.0.0.1.evil.example:8765/signin/done",
  "https://127.0.0.1:8765/signin/done",
  "http://localhost:8765/signin/done",
  "http://127.0.0.1:80/signin/done",
  "http://127.0.0.1:8765/signin/done?x=1",
  "http://127.0.0.1:8765/other",
  "http://evil.example/signin/done",
  "",
]) {
  assert.equal(validReturn(bad), false, bad);
}
assert.equal(escape("<a href='x'>"), "&#60;a href=&#39;x&#39;&#62;");

async function signinUrl(challenge, extra = {}) {
  const q = new URLSearchParams({ state: STATE, challenge, challenge_method: "S256", return: RETURN, v: "0.0.1", ...extra });
  return `/signin?${q}`;
}

// The sign-in page
let { challenge, verifier } = await pkce();
let r = await handle(req("GET", await signinUrl(challenge)), env, NOW);
assert.equal(r.status, 200);
assert.match(await text(r), /Work email/);
assert.equal(r.headers.get("Referrer-Policy"), "no-referrer");
assert.match(r.headers.get("Content-Security-Policy"), /form-action 'self' http:\/\/127\.0\.0\.1:\*/);
r = await handle(req("GET", await signinUrl(challenge, { return: "http://evil.example/signin/done" })), env, NOW);
assert.equal(r.status, 400);
r = await handle(req("GET", await signinUrl(challenge, { challenge_method: "plain" })), env, NOW);
assert.equal(r.status, 400);

// An address with no license gets the same answer and no email
const ask = (email, c = challenge) => req("POST", "/signin", form({ email, state: STATE, challenge: c, return: RETURN }));
r = await handle(ask("nobody@lab.example"), env, NOW);
assert.equal(r.status, 200);
assert.match(await text(r), /If nobody@lab\.example holds a Mabillon license/);
assert.equal(emails.length, 0);
r = await handle(req("POST", "/signin", form({ email: "expert@lab.example", state: STATE, challenge, return: "http://evil.example/" })), env, NOW);
assert.equal(r.status, 400);
assert.equal(emails.length, 0);

// A licensed address gets one link by email
r = await handle(ask("Expert@Lab.example "), env, NOW);
assert.equal(r.status, 200);
assert.equal(emails.length, 1);
assert.deepEqual(emails[0].to, ["expert@lab.example"]);
const link = /https:\/\/account\.getmabillon\.com\/signin\/link\?t=([A-Za-z0-9_-]+)/.exec(emails[0].text)[1];
assert.ok(!JSON.stringify(db.prepare("SELECT * FROM links").all()).includes(link), "only the hash is kept");
assert.match(linkEmail("L", 15), /never sends us anything from your cases/);

// Opening the link (or a mail scanner opening it) does not use it up
for (let i = 0; i < 2; i++) {
  r = await handle(req("GET", `/signin/link?t=${link}`), env, NOW);
  assert.equal(r.status, 200);
  assert.match(await text(r), /Continue to Mabillon/);
}

// Continue: back to the app with a code and the app's own state
r = await handle(req("POST", "/signin/link", form({ t: link })), env, minutes(1));
assert.equal(r.status, 303);
const back = new URL(r.headers.get("Location"));
assert.equal(`${back.origin}${back.pathname}`, RETURN);
assert.equal(back.searchParams.get("state"), STATE);
const code = back.searchParams.get("code");
r = await handle(req("POST", "/signin/link", form({ t: link })), env, minutes(1));
assert.equal(r.status, 400, "a link works once");

// A wrong verifier spends the code: a caught code is no use to anyone else
r = await handle(api("/api/token", { code, verifier: "x".repeat(64), v: "0.0.1" }), env, minutes(2));
assert.equal(r.status, 400);
assert.equal((await r.json()).error, "mismatch");
r = await handle(api("/api/token", { code, verifier, v: "0.0.1" }), env, minutes(2));
assert.equal((await r.json()).error, "used");

// Again, all the way through
async function signIn(at = NOW) {
  ({ challenge, verifier } = await pkce());
  emails.length = 0;
  await handle(ask("expert@lab.example"), env, at);
  const t = /\?t=([A-Za-z0-9_-]+)/.exec(emails[0].text)[1];
  const back = new URL((await handle(req("POST", "/signin/link", form({ t })), env, at)).headers.get("Location"));
  return handle(api("/api/token", { code: back.searchParams.get("code"), verifier, v: "0.0.1" }), env, at);
}

r = await signIn();
assert.equal(r.status, 200);
const issued = await r.json();
assert.equal(typeof issued.token, "string");
const lic = JSON.parse(issued.license);
assert.deepEqual(lic, {
  v: 1,
  aud: "mabillon",
  kid: "k1",
  id: "lic_abcdefgh1234",
  email: "expert@lab.example",
  plan: "pilot",
  issued_at: NOW.toISOString(),
  expires: "2027-11-06T00:00:00.000Z",
  offline: false,
});
const sig = Uint8Array.from(atob(issued.signature.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
assert.ok(await crypto.subtle.verify({ name: "Ed25519" }, keys.publicKey, sig, new TextEncoder().encode(issued.license)));
const tokens = db.prepare("SELECT * FROM tokens").all();
assert.equal(tokens.length, 1);
assert.notEqual(tokens[0].hash, issued.token, "only the token's hash is kept");
assert.deepEqual(Object.keys(tokens[0]).sort(), ["app_version", "created_at", "hash", "last_renewed_at", "license_id"]);

// Renewal
r = await handle(api("/api/renew", { license_id: lic.id, token: issued.token, v: "0.0.2" }), env, minutes(60 * 24 * 3));
assert.equal(r.status, 200);
const renewed = JSON.parse((await r.json()).license);
assert.equal(renewed.issued_at, minutes(60 * 24 * 3).toISOString());
assert.equal(db.prepare("SELECT app_version FROM tokens").get().app_version, "0.0.2");
r = await handle(api("/api/renew", { license_id: lic.id, token: "wrong".repeat(8), v: "0.0.2" }), env, NOW);
assert.equal(r.status, 401);
r = await handle(api("/api/renew", { license_id: "lic_zzzzzzzz9999", token: issued.token, v: "0.0.2" }), env, NOW);
assert.equal(r.status, 401, "a token renews only its own license");

// Revoked or ended: no renewal, no new sign-in
db.prepare("UPDATE licenses SET status = 'revoked'").run();
r = await handle(api("/api/renew", { license_id: lic.id, token: issued.token, v: "0.0.2" }), env, NOW);
assert.equal(r.status, 403);
emails.length = 0;
await handle(ask("expert@lab.example"), env, NOW);
assert.equal(emails.length, 0);
db.prepare("UPDATE licenses SET status = 'active'").run();
r = await handle(api("/api/renew", { license_id: lic.id, token: issued.token, v: "0.0.2" }), env, new Date("2027-11-07T00:00:00Z"));
assert.equal(r.status, 403);

// Sign out drops the token
r = await handle(api("/api/signout", { license_id: lic.id, token: issued.token }), env, NOW);
assert.equal(r.status, 204);
r = await handle(api("/api/renew", { license_id: lic.id, token: issued.token, v: "0.0.2" }), env, NOW);
assert.equal(r.status, 401);

// Links and codes time out
({ challenge, verifier } = await pkce());
emails.length = 0;
await handle(ask("expert@lab.example"), env, NOW);
const late = /\?t=([A-Za-z0-9_-]+)/.exec(emails[0].text)[1];
r = await handle(req("POST", "/signin/link", form({ t: late })), env, minutes(16));
assert.equal(r.status, 400);
emails.length = 0;
await handle(ask("expert@lab.example"), env, NOW);
const slow = /\?t=([A-Za-z0-9_-]+)/.exec(emails[0].text)[1];
const slowBack = new URL((await handle(req("POST", "/signin/link", form({ t: slow })), env, NOW)).headers.get("Location"));
r = await handle(api("/api/token", { code: slowBack.searchParams.get("code"), verifier, v: "0.0.1" }), env, minutes(6));
assert.equal(r.status, 400);

// Junk
for (const bad of ["[]", "{", JSON.stringify({ code: 1 }), JSON.stringify({ code: "c", verifier: "short", v: "1" })]) {
  r = await handle(req("POST", "/api/token", bad, { "Content-Type": "application/json" }), env, NOW);
  assert.equal(r.status, 400, bad);
}
r = await handle(req("GET", "/nothing"), env, NOW);
assert.equal(r.status, 404);

console.log("license worker: all tests passed");
