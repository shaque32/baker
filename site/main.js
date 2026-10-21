// Plays the hero demo: three example claims, one after another. Without this script the first
// example shows in full; with reduced motion the tabs still work but nothing plays on its own.
(function () {
  const demo = document.getElementById("demo");
  if (!demo) return;
  const tabs = Array.from(demo.querySelectorAll('[role="tab"]'));
  const scenes = tabs.map((t) => document.getElementById(t.getAttribute("aria-controls")));
  const marks = Array.from(demo.querySelectorAll("mark[data-for]"));
  const audit = demo.querySelector(".audit");
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const letters = ["a", "b", "c"];
  let current = 0;
  let timer = null;
  let visible = true;
  let userTook = false;

  function show(i) {
    current = i;
    tabs.forEach((t, k) => t.setAttribute("aria-selected", String(k === i)));
    scenes.forEach((s, k) => { s.hidden = k !== i; });
    marks.forEach((m) => m.classList.toggle("on", m.dataset.for.split(" ").includes(letters[i])));
    if (still) return;
    audit.classList.remove("play");
    void audit.offsetWidth; // restart the CSS animations
    audit.classList.add("play");
  }

  function schedule() {
    clearTimeout(timer);
    if (still || userTook || !visible) return;
    timer = setTimeout(() => { show((current + 1) % tabs.length); schedule(); }, 6500);
  }

  tabs.forEach((t, i) => {
    t.addEventListener("click", () => { userTook = true; clearTimeout(timer); show(i); });
    t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const n = (i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
      tabs[n].focus();
      tabs[n].click();
    });
  });

  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      schedule();
    }, { threshold: 0.3 }).observe(demo);
  }
  show(0);
  schedule();
})();
