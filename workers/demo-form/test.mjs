// Run with: node workers/demo-form/test.mjs  (no dependencies)
import assert from "node:assert/strict";
import { validate, buildMime } from "./src/index.js";

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
console.log("demo-form tests passed");
