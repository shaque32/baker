// Steps the home page walkthrough as you scroll: each step shows one stage of the example claim.
// Without this script the panel shows the finished first claim; reduced motion only drops the fades.
(function () {
  const walk = document.getElementById("walk");
  if (!walk || !("IntersectionObserver" in window)) return;
  const steps = Array.from(walk.querySelectorAll(".walk-step"));
  const parts = Array.from(walk.querySelectorAll("[data-on]")).map((el) => {
    const [a, b] = el.dataset.on.split("-").map(Number);
    return { el, from: a, to: b || a };
  });

  function show(n) {
    steps.forEach((s) => s.classList.toggle("on", Number(s.dataset.step) === n));
    parts.forEach((p) => p.el.classList.toggle("on", n >= p.from && n <= p.to));
  }

  walk.classList.add("live");
  show(1);
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) show(Number(e.target.dataset.step)); });
  }, { rootMargin: "-50% 0px -50% 0px" });
  steps.forEach((s) => io.observe(s));
})();
