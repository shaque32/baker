// Steps the home page walkthrough as you scroll: each step shows one stage of the example claim.
// Without this script the panel shows the finished first claim; reduced motion only drops the fades.
(function () {
  const walk = document.getElementById("walk");
  if (!walk) return;
  const steps = Array.from(walk.querySelectorAll(".walk-step"));
  const parts = Array.from(walk.querySelectorAll("[data-on]")).map((el) => {
    const [a, b] = el.dataset.on.split("-").map(Number);
    return { el, from: a, to: b || a };
  });

  function show(n) {
    steps.forEach((s) => s.classList.toggle("on", Number(s.dataset.step) === n));
    parts.forEach((p) => p.el.classList.toggle("on", n >= p.from && n <= p.to));
  }

  // The step whose box holds the middle of the viewport is the current one. Measured in pixels on
  // scroll, since percentage observer margins do not resolve against height in every browser.
  let current = 0;
  let queued = false;
  function update() {
    queued = false;
    const mid = window.innerHeight / 2;
    let n = 1;
    steps.forEach((s) => { if (s.getBoundingClientRect().top <= mid) n = Number(s.dataset.step); });
    if (n !== current) { current = n; show(n); }
  }
  function queue() { if (!queued) { queued = true; requestAnimationFrame(update); } }

  walk.classList.add("live");
  update();
  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", queue);
})();
