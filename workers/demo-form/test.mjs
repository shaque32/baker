// Run with: node workers/demo-form/test.mjs  (no dependencies)
import assert from "node:assert/strict";
import worker, { validate, buildMime, displayName } from "./src/index.js";

const form = (o) => ({ get: (k) => o[k] ?? null });

let r = validate(form({ first_name: "Ana", last_name: "Lee", email: "ana@lab.example", role: "Forensic examiner", message: "Hi" }));
assert.deepEqual(r.errors, []);

r = validate(form({ first_name: "", last_name: "Lee", email: "nope" }));
assert.deepEqual(r.errors, ["first name", "work email"]);

r = validate(form({ first_name: "Ana\r\nBcc: x@y.z", last_name: "Lee", email: "a@b.co\r\nBcc: x@y.z" }));
assert.ok(!r.fields.first.includes("\n"));
assert.ok(!r.fields.email.includes("\n"));
assert.ok(r.errors.includes("work email"), "an email carrying a header is rejected");

r = validate(form({ first_name: "A", last_name: "B", email: "a@b.co", role: "CEO" }));
assert.equal(r.fields.role, "Other");

const mime = buildMime(
  { first: "José", last: "Núñez", email: "j@b.co", role: "", message: "line1\nline2" },
  { from: "demo-form@getmabillon.com", to: "inbox@example.com", now: new Date(0), id: "x" },
);
const headers = mime.split("\r\n\r\n")[0];
assert.match(headers, /^Subject: =\?UTF-8\?B\?/m);
assert.match(headers, /^Reply-To: =\?UTF-8\?B\?.*\?= <j@b\.co>$/m);
assert.equal(headers.split("\r\n").length, 9);
// A comma, "<" or "@" in a name stays inside one quoted display name.
const evil = buildMime(
  { first: 'x@evil.example, "Bob', last: "Lee <x@evil.example>", email: "a@b.co", role: "", message: "" },
  { from: "f@getmabillon.com", to: "t@example.com", now: new Date(0), id: "y" },
);
assert.match(evil, /^Reply-To: "x@evil\.example, \\"Bob Lee <x@evil\.example>" <a@b\.co>$/m);
assert.equal(displayName('a\\b'), '"a\\\\b"');

// The handler, up to the send (no NOTIFY_TO, so it answers 503 once the checks pass).
const env = { SITE: "https://getmabillon.com", FROM: "f@getmabillon.com" };
const good = { first_name: "Ana", last_name: "Lee", email: "ana@lab.example", role: "Other" };
const post = (headers, fields = good) =>
  worker.fetch(
    new Request("https://forms.getmabillon.com/demo", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", ...headers },
      body: new URLSearchParams(fields).toString(),
    }),
    env,
  );

assert.equal((await post({ origin: "null" })).status, 503, "Origin: null is accepted");
assert.equal((await post({})).status, 503, "no Origin is accepted");
assert.equal((await post({ origin: "https://getmabillon.com" })).status, 503);
assert.equal((await post({ origin: "https://www.getmabillon.com" })).status, 503);
assert.equal((await post({ origin: "https://evil.example" })).status, 403);
const trapped = await post({ origin: "null" }, { ...good, website: "x" });
assert.equal(trapped.status, 303);
assert.equal(trapped.headers.get("location"), "https://getmabillon.com/demo-thanks.html");
assert.equal((await post({ origin: "null" }, { ...good, email: "bad" })).status, 400);

// The rate limit answers 429 once the binding says no.
let calls = 0;
const limited = { ...env, LIMITER: { limit: async ({ key }) => ({ success: key === "1.2.3.4" && ++calls <= 1 }) } };
const send = () =>
  worker.fetch(
    new Request("https://forms.getmabillon.com/demo", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", "cf-connecting-ip": "1.2.3.4" },
      body: new URLSearchParams(good).toString(),
    }),
    limited,
  );
assert.equal((await send()).status, 503);
assert.equal((await send()).status, 429);

console.log("demo-form tests passed");
