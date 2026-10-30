// Drives the home page: fades sections in on first sight, and runs the one-claim walk as a
// stepper. Progress is a fractional value from 1 to 5.95; every panel part's data-on grammar
// is unchanged, only what moves the dial. Autoplay suggests the rhythm; the pointer, focus,
// pause button, keys, or a tab click take it over at any moment.
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
  const panel = document.getElementById("walk");
  if (!panel) return;
  const tabs = Array.from(panel.querySelectorAll(".stepper button"));
  if (!tabs.length) return;
  const capTitle = panel.querySelector(".panel-caption h3");
  const capText = panel.querySelector(".panel-caption p");
  const playBtn = panel.querySelector(".walk-play");
  const parts = Array.from(panel.querySelectorAll("[data-on]")).map((el) => {
    const [a, b] = el.dataset.on.split("-");
    return { el, from: Number(a), to: b ? Number(b) : Infinity };
  });

  const STEPS = tabs.length;              // 5
  const CYCLE = 22000;                    // ms for p to run 1 → STEPS + 0.95
  const DWELL = 3000;                     // ms held at the end before looping
  const USER_HOLD = 10000;                // ms autoplay waits after a user action
  const MAX_P = STEPS + 0.95;             // keeps every data-on range reachable

  function timeFor(p) {
    return ((Math.max(1, Math.min(MAX_P, p)) - 1) / (MAX_P - 1)) * CYCLE;
  }
  function progressFor(ts) {
    const clamped = Math.min(ts, CYCLE);
    return 1 + (clamped / CYCLE) * (MAX_P - 1);
  }

  let t = 0;
  let last = null;
  let pointerPaused = false;
  let focusHeld = false;
  let userPaused = false;
  let userHoldUntil = 0;
  let panelVisible = false;
  let hasPlayed = false;

  // The first claim types itself out the first time it becomes visible.
  const typed = panel.querySelector(".claim .claimtext");
  const fullText = typed ? typed.textContent : "";
  let typing = false;
  function type() {
    if (!typed || typing) return;
    typing = true;
    const caret = document.createElement("span");
    caret.className = "walk-caret";
    let i = 0;
    typed.textContent = "";
    typed.append(document.createTextNode(""), caret);
    const int = setInterval(() => {
      i += 1;
      typed.firstChild.textContent = fullText.slice(0, i);
      if (i >= fullText.length) {
        clearInterval(int);
        setTimeout(() => caret.remove(), 1200);
      }
    }, 22);
  }

  let lastCapStep = -1;
  function paint() {
    const p = progressFor(t);
    const n = Math.min(STEPS, Math.max(1, Math.floor(p)));
    const frac = Math.max(0, Math.min(1, p - n));
    tabs.forEach((btn, i) => {
      const stepN = i + 1;
      const active = stepN === n;
      btn.setAttribute("aria-selected", String(active));
      btn.setAttribute("tabindex", active ? "0" : "-1");
      btn.dataset.done = String(stepN < n);
      btn.style.setProperty("--p", active ? String(frac) : "0");
      if (active) panel.querySelector(".walk-panel").setAttribute("aria-labelledby", btn.id);
    });
    if (lastCapStep !== n) {
      lastCapStep = n;
      const active = tabs[n - 1];
      if (active && capTitle && capText) {
        capTitle.textContent = active.dataset.title || "";
        capText.textContent = active.dataset.desc || "";
      }
    }
    parts.forEach((q) => q.el.classList.toggle("on", p >= q.from && p < q.to));
    if (!typing && !still) {
      const claim = typed && typed.parentElement;
      if (claim && claim.classList.contains("on")) type();
    }
  }

  function playing(ts) {
    if (!panelVisible) return false;
    if (pointerPaused || focusHeld || userPaused) return false;
    if (ts < userHoldUntil) return false;
    return true;
  }

  function tick(ts) {
    if (last !== null && playing(ts)) {
      const dt = ts - last;
      t += dt;
      if (t > CYCLE + DWELL) t = 0;
    }
    last = ts;
    // Only paint when the panel is on screen: offscreen advancement wastes work and, more
    // importantly, lets the user re-encounter the walk mid-cycle after scrolling past it.
    if (panelVisible) paint();
    requestAnimationFrame(tick);
  }

  function goToStep(n) {
    const target = Math.max(1, Math.min(STEPS, n));
    // Settle at the end of the step so every part it reveals shows (step 5's verdict starts at
    // 5.6), as it did when the reader scrolled to the bottom of a step.
    const p = Math.min(MAX_P, target + 0.95);
    t = timeFor(p);
    userHoldUntil = performance.now() + USER_HOLD;
    paint();
  }

  tabs.forEach((btn, i) => {
    btn.addEventListener("click", () => {
      goToStep(i + 1);
      btn.focus({ preventScroll: true });
    });
    btn.addEventListener("keydown", (e) => {
      const k = e.key;
      // Arrows move from the step on screen, which is not always the focused tab.
      const cur = Math.max(0, lastCapStep - 1);
      let targetIdx = null;
      if (k === "ArrowRight" || k === "ArrowDown") targetIdx = (cur + 1) % STEPS;
      else if (k === "ArrowLeft" || k === "ArrowUp") targetIdx = (cur - 1 + STEPS) % STEPS;
      else if (k === "Home") targetIdx = 0;
      else if (k === "End") targetIdx = STEPS - 1;
      if (targetIdx === null) return;
      e.preventDefault();
      goToStep(targetIdx + 1);
      tabs[targetIdx].focus({ preventScroll: true });
    });
  });

  panel.addEventListener("pointerenter", () => { pointerPaused = true; });
  panel.addEventListener("pointerleave", () => { pointerPaused = false; });
  // Keyboard focus inside the panel holds autoplay until it leaves, so the step never changes
  // under a keyboard reader. A mouse click focuses a tab too, but only holds for USER_HOLD.
  function keyboardFocus(el) {
    try { return el.matches(":focus-visible"); } catch (err) { return true; }
  }
  panel.addEventListener("focusin", (e) => {
    if (e.target === playBtn) { focusHeld = false; return; }
    focusHeld = keyboardFocus(e.target);
    userHoldUntil = performance.now() + USER_HOLD;
  });
  panel.addEventListener("focusout", (e) => {
    if (!panel.contains(e.relatedTarget)) focusHeld = false;
  });

  if (playBtn) {
    function updatePlayBtn() {
      playBtn.setAttribute("aria-pressed", String(userPaused));
      playBtn.setAttribute("aria-label", userPaused ? "Resume walkthrough" : "Pause walkthrough");
    }
    playBtn.addEventListener("click", () => {
      userPaused = !userPaused;
      userHoldUntil = 0;
      updatePlayBtn();
    });
    updatePlayBtn();
  }

  panel.classList.add("live");
  // One paint at step 1 so the panel renders its initial state immediately — the .live class
  // hides every data-on part until paint() tags the current ones, and without this call the
  // panel reads as empty for the frames between page load and the IO firing.
  paint();

  if (still) {
    // Reduced motion: no autoplay. Settle on step 1 so the walk reads as the first-claim
    // narrative, not the failed-check ending. The examiner steps at will.
    userPaused = true;
    if (playBtn) playBtn.hidden = true;
    panelVisible = true;
    // Progress 1 shows nothing (the first claim starts at 1.4), so start at the end of step 1.
    t = timeFor(1.95);
    paint();
    return;
  }

  // Only let the clock advance while the panel is actually on screen. Without this gate the
  // walk cycles continuously in the background: the user scrolls down from the hero and lands
  // on the panel mid-cycle, and while scrolling past, the panel contents keep moving against
  // the scroll — two motions reading as jitter.
  if ("IntersectionObserver" in window) {
    const vis = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        panelVisible = e.isIntersecting;
        if (panelVisible && !hasPlayed) {
          // First arrival: run the walk from the beginning so the examiner catches the full arc.
          hasPlayed = true;
          t = 0;
        }
        if (panelVisible) paint();
      });
    }, { threshold: 0.45 });
    vis.observe(panel);
  } else {
    panelVisible = true;
  }

  requestAnimationFrame(tick);
})();
