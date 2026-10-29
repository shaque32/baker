// The Book a demo form. A sent form shows "Sending…" and can't be sent twice. If the form
// handler sends the visitor back (?error=…), this shows why and refills what they typed, from a
// copy kept in this tab only (sessionStorage) and deleted once the request goes through.
(() => {
  const KEY = "mabillon-demo-form";
  const FIELDS = ["first_name", "last_name", "email", "role", "message"];
  const MESSAGES = {
    invalid: "Please check the fields marked below.",
    busy: "Too many requests from your connection. Please wait a minute and try again.",
    unreadable: "We could not read the form. Please try again.",
    unavailable: "We could not send that just now. Please try again, or email support@getmabillon.com.",
  };

  const store = {
    get() { try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (err) { return null; } },
    set(v) { try { sessionStorage.setItem(KEY, JSON.stringify(v)); } catch (err) { /* private mode */ } },
    clear() { try { sessionStorage.removeItem(KEY); } catch (err) { /* private mode */ } },
  };

  const form = document.querySelector(".demo-form");
  // The thanks page loads this too: the request went through, so the copy goes.
  if (!form) { store.clear(); return; }

  const button = form.querySelector('button[type="submit"]');
  const label = button.textContent;
  const params = new URLSearchParams(location.search);
  const code = params.get("error");

  if (code && MESSAGES[code]) {
    const saved = store.get();
    if (saved) for (const name of FIELDS) if (saved[name] != null) form.elements[name].value = saved[name];
    const bad = (params.get("fields") || "").split(",").filter((n) => FIELDS.includes(n));
    for (const name of bad) form.elements[name].setAttribute("aria-invalid", "true");
    const note = form.querySelector(".form-error");
    note.textContent = MESSAGES[code];
    note.hidden = false;
    (bad.length ? form.elements[bad[0]] : button).focus();
  } else {
    store.clear();
  }

  form.addEventListener("input", (e) => e.target.removeAttribute("aria-invalid"));

  // The submit event only fires once the browser's own checks pass.
  form.addEventListener("submit", (e) => {
    if (button.disabled) { e.preventDefault(); return; }
    const copy = {};
    for (const name of FIELDS) copy[name] = form.elements[name].value;
    store.set(copy);
    button.disabled = true;
    button.textContent = "Sending…";
    form.setAttribute("aria-busy", "true");
  });

  // Coming back with the browser's back button restores this page from cache with the button
  // still disabled.
  window.addEventListener("pageshow", () => {
    button.disabled = false;
    button.textContent = label;
    form.removeAttribute("aria-busy");
  });
})();
