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
    `Reply-To: ${encodeHeader(name)} <${f.email}>`,
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

function page(status, title, text, site) {
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${title} · Mabillon</title>
<link rel="stylesheet" href="${site}/styles.css"></head><body><main class="prose"><div class="wrap"><article>
<h1>${title}</h1><p>${text}</p><p><a href="${site}/demo.html">Back to the form</a></p>
</article></div></main></body></html>`;
  return new Response(html, { status, headers: { "content-type": "text/html; charset=utf-8" } });
}

export default {
  async fetch(request, env) {
    const site = env.SITE;
    const url = new URL(request.url);
    if (url.pathname !== "/demo") return new Response("Not found", { status: 404 });
    if (request.method !== "POST") return Response.redirect(`${site}/demo.html`, 303);

    const origin = request.headers.get("origin") || "";
    const allowed = [site, site.replace("https://", "https://www.")];
    if (origin && !allowed.includes(origin)) return new Response("Forbidden", { status: 403 });

    let form;
    try {
      form = await request.formData();
    } catch {
      return page(400, "Something went wrong", "We could not read the form. Please try again.", site);
    }
    const { fields, errors } = validate(form);
    // A filled hidden field means a bot: answer as if it worked, send nothing.
    if (fields.trap) return Response.redirect(`${site}/demo-thanks.html`, 303);
    if (errors.length) {
      return page(400, "Please check the form", `Missing or invalid: ${errors.join(", ")}.`, site);
    }
    if (!env.NOTIFY_TO) {
      return page(503, "Form not set up yet", "Please email support@getmabillon.com instead.", site);
    }

    try {
      const { EmailMessage } = await import("cloudflare:email");
      const raw = buildMime(fields, { from: env.FROM, to: env.NOTIFY_TO });
      await env.MAIL.send(new EmailMessage(env.FROM, env.NOTIFY_TO, raw));
    } catch (err) {
      console.error("send failed", err && err.message);
      return page(502, "We could not send that", "Please email support@getmabillon.com instead.", site);
    }
    return Response.redirect(`${site}/demo-thanks.html`, 303);
  },
};
