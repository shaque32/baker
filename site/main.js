// Builds the home page walkthrough as you scroll. Progress runs from 1 to 6: the step whose box
// holds the middle of the viewport, plus how far through that step the reader is. Each panel part
// shows while progress is inside its data-on range ("a-b", or "a-" for no end). Without this
// script the panel shows the finished first claim; reduced motion only drops the fades.
const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Sections play once, when about a third of them is on screen.
(function () {
  document.documentElement.classList.add("js");
  const items = Array.from(document.querySelectorAll(".reveal"));
  if (still || !("IntersectionObserver" in window)) {
    items.forEach((el) => el.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in");
      io.unobserve(e.target);
    });
  }, { threshold: 0.33 });
  items.forEach((el) => io.observe(el));
})();

(function () {
  const walk = document.getElementById("walk");
  if (!walk) return;
  const steps = Array.from(walk.querySelectorAll(".walk-step"));
  const rail = Array.from(walk.querySelectorAll(".rail li"));
  // On narrow screens the panel covers the step text, so the panel repeats the current step.
  const capTitle = walk.querySelector(".panel-caption h3");
  const capText = walk.querySelector(".panel-caption p");
  const parts = Array.from(walk.querySelectorAll("[data-on]")).map((el) => {
    const [a, b] = el.dataset.on.split("-");
    return { el, from: Number(a), to: b ? Number(b) : Infinity };
  });
  let queued = false;

  // The first claim types itself out the first time it appears.
  const typed = walk.querySelector(".claim .claimtext");
  const full = typed.textContent;
  let typing = false;
  function type() {
    typing = true;
    const caret = document.createElement("span");
    caret.className = "caret";
    let i = 0;
    typed.textContent = "";
    typed.append(document.createTextNode(""), caret);
    const t = setInterval(() => {
      i += 1;
      typed.firstChild.textContent = full.slice(0, i);
      if (i >= full.length) {
        clearInterval(t);
        setTimeout(() => caret.remove(), 1400);
      }
    }, 22);
  }

  function progress() {
    // Measured in pixels on scroll, since percentage observer margins do not resolve against
    // height in every browser.
    const mid = window.innerHeight / 2;
    let p = 1;
    steps.forEach((s, i) => {
      const r = s.getBoundingClientRect();
      if (r.top <= mid) p = i + 1 + Math.min(0.999, (mid - r.top) / Math.max(1, r.height));
    });
    return p;
  }

  function update() {
    queued = false;
    const p = progress();
    const n = Math.floor(p);
    steps.forEach((s, i) => s.classList.toggle("on", i + 1 === n));
    const cur = steps[n - 1];
    if (cur && capTitle.dataset.step !== String(n)) {
      capTitle.dataset.step = String(n);
      capTitle.textContent = `${n}. ${cur.querySelector("h3").textContent}`;
      capText.textContent = cur.querySelector("p").textContent;
    }
    rail.forEach((r, i) => { r.classList.toggle("on", i + 1 === n); r.classList.toggle("done", i + 1 < n); });
    parts.forEach((q) => q.el.classList.toggle("on", p >= q.from && p < q.to));
    if (!typing && !still && typed.parentElement.classList.contains("on")) type();
  }
  function queue() { if (!queued) { queued = true; requestAnimationFrame(update); } }

  walk.classList.add("live");
  update();
  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", queue);
})();
