/* Lightweight motion system adapted from the original OneCare Loop UI.
   No third-party animation runtime is required; respects reduced-motion settings. */
(() => {
  "use strict";
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  let observer = null;

  function reveal(scope = document) {
    const elements = [];
    if (scope instanceof Element && scope.matches(".oc-motion-reveal")) elements.push(scope);
    if (scope.querySelectorAll) elements.push(...scope.querySelectorAll(".oc-motion-reveal"));
    if (reduceMotion || !("IntersectionObserver" in window)) {
      elements.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    if (!observer) {
      observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.12, rootMargin: "0px 0px -28px 0px" });
    }
    elements.forEach((el) => observer.observe(el));
  }

  function stagger(scope = document) {
    const groups = [];
    if (scope instanceof Element && scope.matches(".oc-stagger")) groups.push(scope);
    if (scope.querySelectorAll) groups.push(...scope.querySelectorAll(".oc-stagger"));
    groups.forEach((group) => [...group.children].forEach((child, index) => {
      child.style.setProperty("--oc-index", String(index));
    }));
  }

  // Delegated ripple keeps working for buttons inserted later by the SPA.
  document.addEventListener("click", (event) => {
    if (reduceMotion) return;
    const button = event.target.closest(".btn, .nav-btn");
    if (!button || button.disabled) return;
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.65;
    const ripple = document.createElement("span");
    ripple.className = "oc-ripple";
    ripple.style.width = `${size}px`;
    ripple.style.height = `${size}px`;
    ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
    button.classList.add("oc-ripple-host");
    button.appendChild(ripple);
    window.setTimeout(() => ripple.remove(), 650);
  });

  // Desktop custom cursor: the original paired dot/ring treatment, without a framework.
  function initCursor() {
    if (reduceMotion || !window.matchMedia?.("(pointer: fine)").matches) return;
    if (document.querySelector(".oc-cursor-dot")) return;
    const dot = document.createElement("span");
    const ring = document.createElement("span");
    dot.className = "oc-cursor-dot";
    ring.className = "oc-cursor-ring";
    dot.setAttribute("aria-hidden", "true");
    ring.setAttribute("aria-hidden", "true");
    document.body.append(dot, ring);
    document.documentElement.classList.add("oc-has-cursor");
    let x = -100, y = -100, rx = x, ry = y, active = true;
    document.addEventListener("pointermove", (event) => {
      x = event.clientX; y = event.clientY;
      dot.style.left = `${x}px`; dot.style.top = `${y}px`;
    }, { passive: true });
    document.addEventListener("pointerover", (event) => {
      if (event.target.closest?.("a, button, input, select, textarea, [role='button']")) ring.classList.add("is-hovering");
    });
    document.addEventListener("pointerout", (event) => {
      if (event.target.closest?.("a, button, input, select, textarea, [role='button']")) ring.classList.remove("is-hovering");
    });
    document.addEventListener("pointerdown", () => ring.classList.add("is-pressed"));
    document.addEventListener("pointerup", () => ring.classList.remove("is-pressed"));
    document.addEventListener("pointerleave", () => { active = false; dot.style.opacity = "0"; ring.style.opacity = "0"; });
    document.addEventListener("pointerenter", () => { active = true; dot.style.opacity = "1"; ring.style.opacity = "1"; });
    const animate = () => {
      if (!active) { requestAnimationFrame(animate); return; }
      rx += (x - rx) * .17; ry += (y - ry) * .17;
      ring.style.left = `${rx}px`; ring.style.top = `${ry}px`;
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }

  // Light magnetic pull for primary actions on pointer devices.
  function initMagnetic(scope = document) {
    if (reduceMotion || !window.matchMedia?.("(pointer: fine)").matches) return;
    const buttons = [];
    if (scope instanceof Element && scope.matches("[data-magnetic]")) buttons.push(scope);
    if (scope.querySelectorAll) buttons.push(...scope.querySelectorAll("[data-magnetic]"));
    buttons.forEach((button) => {
      if (button.dataset.ocMagneticReady === "true") return;
      button.dataset.ocMagneticReady = "true";
      button.addEventListener("pointermove", (event) => {
        const rect = button.getBoundingClientRect();
        const dx = event.clientX - rect.left - rect.width / 2;
        const dy = event.clientY - rect.top - rect.height / 2;
        button.style.transform = `translate3d(${dx * .10}px, ${dy * .14}px, 0)`;
      });
      button.addEventListener("pointerleave", () => { button.style.transform = ""; });
      button.addEventListener("pointercancel", () => { button.style.transform = ""; });
    });
  }

  // Ambient particle field for the landing hero. Kept deliberately small for low-spec devices.
  function initParticles(scope = document) {
    const canvases = [];
    if (scope instanceof Element && scope.matches("canvas[data-oc-particles]")) canvases.push(scope);
    if (scope.querySelectorAll) canvases.push(...scope.querySelectorAll("canvas[data-oc-particles]"));
    canvases.forEach((canvas) => {
      if (canvas.dataset.ocParticlesReady === "true" || reduceMotion) return;
      canvas.dataset.ocParticlesReady = "true";
      const context = canvas.getContext("2d");
      if (!context) return;
      const host = canvas.parentElement;
      let width = 0, height = 0, frame = 0;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const count = Math.min(34, Math.max(18, Math.round((host.clientWidth * host.clientHeight) / 38000)));
      const points = Array.from({ length: count }, () => ({
        x: Math.random(), y: Math.random(), vx: (Math.random() - .5) * .00012, vy: (Math.random() - .5) * .00012, r: Math.random() * 1.2 + .45,
      }));
      const resize = () => {
        const rect = host.getBoundingClientRect();
        width = Math.max(1, rect.width); height = Math.max(1, rect.height);
        canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
        canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
        context.setTransform(dpr, 0, 0, dpr, 0, 0);
      };
      const draw = () => {
        context.clearRect(0, 0, width, height);
        points.forEach((point, index) => {
          point.x += point.vx; point.y += point.vy;
          if (point.x < 0 || point.x > 1) point.vx *= -1;
          if (point.y < 0 || point.y > 1) point.vy *= -1;
          const x = point.x * width, y = point.y * height;
          context.beginPath(); context.arc(x, y, point.r, 0, Math.PI * 2);
          context.fillStyle = "rgba(94, 220, 190, .48)"; context.fill();
          for (let j = index + 1; j < points.length; j++) {
            const other = points[j];
            const ox = other.x * width, oy = other.y * height;
            const distance = Math.hypot(x - ox, y - oy);
            if (distance < 112) {
              context.beginPath(); context.moveTo(x, y); context.lineTo(ox, oy);
              context.strokeStyle = `rgba(65, 175, 155, ${(1 - distance / 112) * .12})`;
              context.lineWidth = .7; context.stroke();
            }
          }
        });
        frame = requestAnimationFrame(draw);
      };
      resize(); draw();
      window.addEventListener("resize", resize, { passive: true });
      document.addEventListener("visibilitychange", () => {
        if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
        else if (!document.hidden && !frame) frame = requestAnimationFrame(draw);
      });
    });
  }

  // Count-up for factual numeric values only; caller provides data-count-to explicitly.
  function countUp(el) {
    if (el.dataset.ocCounted === "true") return;
    const target = Number(el.dataset.countTo);
    if (!Number.isFinite(target)) return;
    el.dataset.ocCounted = "true";
    if (reduceMotion) { el.textContent = String(target); return; }
    const duration = Math.min(1800, Math.max(450, Number(el.dataset.duration) || 1100));
    const started = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = target * eased;
      el.textContent = Number.isInteger(target) ? Math.round(value).toLocaleString() : value.toFixed(1);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function refresh(scope = document) {
    const revealSelectors = [".page-intro", ".grid > .card", ".grid > section.card", ".notice", ".table-wrap", ".oc-journey-panel", ".empty", ".auth-card"];
    revealSelectors.forEach((selector) => {
      const nodes = [];
      if (scope instanceof Element && scope.matches(selector)) nodes.push(scope);
      if (scope.querySelectorAll) nodes.push(...scope.querySelectorAll(selector));
      nodes.forEach((el) => {
        if (el.dataset.ocRevealReady !== "true") {
          el.dataset.ocRevealReady = "true";
          el.classList.add("oc-motion-reveal");
        }
      });
    });
    [".grid", ".auth-facts"].forEach((selector) => {
      const groups = [];
      if (scope instanceof Element && scope.matches(selector)) groups.push(scope);
      if (scope.querySelectorAll) groups.push(...scope.querySelectorAll(selector));
      groups.forEach((group) => group.classList.add("oc-stagger"));
    });
    reveal(scope);
    stagger(scope);
    initMagnetic(scope);
    initParticles(scope);
    if (scope.querySelectorAll) scope.querySelectorAll("[data-count-to]").forEach(countUp);
    if (scope instanceof Element && scope.matches("[data-count-to]")) countUp(scope);
  }

  window.OneCareMotion = { refresh };

  function boot() {
    initCursor();
    refresh(document);
    if ("MutationObserver" in window && !window.__oneCareMotionObserver) {
      const mutationObserver = new MutationObserver((records) => {
        records.forEach((record) => record.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) refresh(node);
        }));
      });
      mutationObserver.observe(document.body, { childList: true, subtree: true });
      window.__oneCareMotionObserver = mutationObserver;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
