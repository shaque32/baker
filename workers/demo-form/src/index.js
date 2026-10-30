// Handles POST /demo from the site's "Book a demo" page and emails it to the team
// (env.NOTIFY_TO, a secret) through the Email Routing send_email binding. Nothing is stored.

const LIMITS = { first: 80, last: 80, email: 200, role: 40, message: 2000 };
const ROLES = ["Forensic examiner", "Defense attorney", "Other"];
const EMAIL_RE = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;

export function clean(value, max) {
  return String(value ?? "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
    .trim()
    .slice(0, max);
}

// One line: no CR or LF can reach a mail header.
export function oneLine(value) {
  return value.replace(/[\r\n]+/g, " ").trim();
}

export function validate(form) {
  const f = {
    first: oneLine(clean(form.get("first_name"), LIMITS.first)),
    last: oneLine(clean(form.get("last_name"), LIMITS.last)),
    email: oneLine(clean(form.get("email"), LIMITS.email)),
    role: oneLine(clean(form.get("role"), LIMITS.role)),
    message: clean(form.get("message"), LIMITS.message),
    trap: clean(form.get("website"), 200),
  };
  const errors = [];
  if (!f.first) errors.push("first name");
  if (!f.last) errors.push("last name");
  if (!EMAIL_RE.test(f.email)) errors.push("work email");
  if (f.role && !ROLES.includes(f.role)) f.role = "Other";
  return { fields: f, errors };
}

// A display name for an address header: an RFC 2047 encoded word outside ASCII, otherwise a
// quoted string, so a comma, "<" or "@" in a name can never add a second address.
export function displayName(text) {
  if (!/^[\x20-\x7e]*$/.test(text)) return encodeHeader(text);
  return `"${text.replace(/[\\"]/g, (c) => `\\${c}`)}"`;
}

function encodeHeader(text) {
  // RFC 2047 encoded word, so names outside ASCII survive.
  if (/^[\x20-\x7e]*$/.test(text)) return text;
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return `=?UTF-8?B?${btoa(bin)}?=`;
}

export function buildMime(f, { from, to, now = new Date(), id = crypto.randomUUID() }) {
  const name = `${f.first} ${f.last}`;
  const body = [
    "New demo request from getmabillon.com",
    "",
    `Name:  ${name}`,
    `Email: ${f.email}`,
    `Role:  ${f.role || "(not given)"}`,
    "",
    "What brings them here:",
    f.message || "(left blank)",
    "",
    "Reply to this email to answer them directly.",
  ].join("\r\n");
  return [
    `From: Mabillon demo form <${from}>`,
    `To: <${to}>`,
    `Reply-To: ${displayName(name)} <${f.email}>`,
    `Subject: ${encodeHeader(`Demo request: ${name}`)}`,
    `Date: ${now.toUTCString()}`,
    `Message-ID: <${id}@getmabillon.com>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    body,
  ].join("\r\n");
}

// Every problem a visitor can fix or retry goes back to the form, which shows the message in the
// site's own style and refills what they typed (site/demo.js). Codes: invalid (with the bad
// fields), busy, unreadable, unavailable.
const FIELD_CODES = { "first name": "first_name", "last name": "last_name", "work email": "email" };

export function backToForm(site, code, fields = []) {
  const q = new URLSearchParams({ error: code });
  if (fields.length) q.set("fields", fields.map((f) => FIELD_CODES[f]).join(","));
  return Response.redirect(`${site}/demo.html?${q}#form`, 303);
}

export default {
  async fetch(request, env) {
    const site = env.SITE;
    const url = new URL(request.url);
    if (url.pathname !== "/demo") return new Response("Not found", { status: 404 });
    if (request.method !== "POST") return Response.redirect(`${site}/demo.html`, 303);

    // A browser sends "null" or no Origin under some referrer and privacy settings, so only a
    // named other site is refused. The honeypot and the rate limit handle the rest.
    const origin = request.headers.get("origin") || "null";
    const allowed = ["null", site, site.replace("https://", "https://www.")];
    if (!allowed.includes(origin)) return new Response("Forbidden", { status: 403 });

    // A few requests a minute per address (the LIMITER binding in wrangler.toml).
    if (env.LIMITER) {
      const ip = request.headers.get("cf-connecting-ip") || "unknown";
      const { success } = await env.LIMITER.limit({ key: ip });
      if (!success) {
        return backToForm(site, "busy");
      }
    }

    let form;
    try {
      form = await request.formData();
    } catch {
      return backToForm(site, "unreadable");
    }
    const { fields, errors } = validate(form);
    // A filled hidden field means a bot: answer as if it worked, send nothing.
    if (fields.trap) return Response.redirect(`${site}/demo-thanks.html`, 303);
    if (errors.length) return backToForm(site, "invalid", errors);
    if (!env.NOTIFY_TO) {
      console.error("NOTIFY_TO is not set");
      return backToForm(site, "unavailable");
    }

    try {
      const { EmailMessage } = await import("cloudflare:email");
      const raw = buildMime(fields, { from: env.FROM, to: env.NOTIFY_TO });
      await env.MAIL.send(new EmailMessage(env.FROM, env.NOTIFY_TO, raw));
    } catch (err) {
      console.error("send failed", err && err.message);
      return backToForm(site, "unavailable");
    }
    return Response.redirect(`${site}/demo-thanks.html`, 303);
  },
};
