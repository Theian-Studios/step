/* STEP: the site's only script. Plain JavaScript, no libraries, no build step.

   Pages are complete HTML without this script; it only adds behavior, so the
   site still works (minus these extras) if it fails to load. Each part below
   checks whether its elements exist on the page and does nothing otherwise.

   What's in here, in order:
     Mobile menu           opens and closes the menu on phones
     Header shadow         adds a shadow once the page scrolls
     Steps grow            the home page's three-step bars grow as they scroll in
     Hero carousel         rotates participant photos on the home page
     Hero photo sizing     lines the carousel up with the headline on wide screens
     Footer year           keeps the copyright year current
     Copy story link       the "Copy link" button on story pages
     Contact form          checks fields, then sends the message (see site.json form_endpoint)

   Anyone who has "reduce motion" turned on gets no animation and a paused carousel. */

(function () {
  /* ---------- Mobile menu ---------- */
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.getElementById("primary-nav");
  if (toggle && nav) {
    const setOpen = (open) => {
      nav.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
    };
    toggle.addEventListener("click", () => setOpen(!nav.classList.contains("is-open")));
    nav.addEventListener("click", (e) => { if (e.target.closest("a")) setOpen(false); });
    document.addEventListener("click", (e) => {
      if (nav.classList.contains("is-open") && !nav.contains(e.target) && !toggle.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && nav.classList.contains("is-open")) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  /* ---------- Header shadow once the page scrolls ---------- */
  const header = document.querySelector(".site-header");
  const onScroll = () => header.classList.toggle("is-scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Steps grow as you scroll ----------
     Each step's progress (0 to 1) follows its position in the window the first
     time it comes into view; once drawn, it stays drawn. */
  const clamp = (v) => Math.min(1, Math.max(0, v));
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const scrollGroups = [
    { list: document.querySelector(".stairs"), items: ".stair", bar: ".stair__bar" },
  ].filter((g) => g.list);
  if (scrollGroups.length && !reduceMotion) {
    let ticking = false;
    const update = () => {
      ticking = false;
      const vh = window.innerHeight;
      scrollGroups.forEach(({ list, items, bar }) => {
        const els = [...list.querySelectorAll(items)];
        const sideBySide = els.length > 1 && Math.abs(els[0].offsetLeft - els[1].offsetLeft) > 10;
        const listTop = list.getBoundingClientRect().top;
        els.forEach((el, i) => {
          let p;
          if (sideBySide) {
            // Columns: build left to right as the row scrolls up the screen.
            p = (vh * 0.92 - listTop) / (vh * 0.45) - i * 0.3;
          } else {
            // Stacked: each step follows its own bar.
            const top = el.querySelector(bar).getBoundingClientRect().top;
            p = (vh * 0.95 - top) / (vh * 0.3);
          }
          // Only ever move forward, so the steps build once and stay drawn.
          const value = Math.max(ease(clamp(p)), el._stepP || 0);
          el._stepP = value;
          el.style.setProperty("--p", value.toFixed(3));
        });
      });
      const done = scrollGroups.every(({ list, items }) => [...list.querySelectorAll(items)].every((el) => el._stepP >= 1));
      if (done) { window.removeEventListener("scroll", request); window.removeEventListener("resize", request); }
    };
    const request = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    scrollGroups.forEach((g) => g.list.classList.add("is-scroll"));
    update();
    window.addEventListener("scroll", request, { passive: true });
    window.addEventListener("resize", request);
  }

  /* ---------- Hero carousel ----------
     Rotates every 4.8 seconds; the dots show who is on screen and jump to a person
     when clicked. Pauses on hover and keyboard focus; motion-sensitive visitors
     start paused. */
  const hc = document.querySelector(".hc");
  if (hc) {
    const slides = [...hc.querySelectorAll(".hc__slide")];
    const tabs = [...hc.querySelectorAll(".hc__dot")];
    const links = [...hc.querySelectorAll(".hc__read")];
    const DURATION = 4800;
    hc.style.setProperty("--hc-time", DURATION + "ms");
    let current = 0, timer = null, userPaused = reduceMotion, held = false;

    // Center the arrows on the photo above the white quote strip, not on the whole slide.
    const centerArrows = () => {
      const card = slides[current].querySelector(".hc__card");
      hc.querySelector(".hc__stage").style.setProperty("--hc-card-h", (card ? card.offsetHeight : 0) + "px");
    };
    // Re-measure whenever a strip changes size (window resize, fonts loading, the photo being resized).
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(centerArrows);
      slides.forEach((s) => s.querySelector(".hc__card") && ro.observe(s.querySelector(".hc__card")));
    } else {
      window.addEventListener("resize", centerArrows);
    }

    // dir: 1 = next (new photo slides in from the right), -1 = previous (from the left).
    const show = (next, dir = 1) => {
      next = (next + slides.length) % slides.length;
      if (next === current) return;
      const leaving = slides[current], entering = slides[next];
      // Put the incoming slide just off-screen on the correct side, without animating.
      entering.style.transition = "none";
      entering.style.transform = `translateX(${dir * 100}%)`;
      void entering.offsetWidth;
      entering.style.transition = entering.style.transform = "";
      entering.classList.add("is-active");
      entering.removeAttribute("aria-hidden");
      // Send the outgoing slide off the opposite side, then park it out of view.
      leaving.classList.remove("is-active");
      leaving.classList.add("is-leaving");
      leaving.style.transform = `translateX(${-dir * 100}%)`;
      leaving.setAttribute("aria-hidden", "true");
      setTimeout(() => {
        if (leaving.classList.contains("is-active")) return;
        leaving.style.transition = "none";
        leaving.classList.remove("is-leaving");
        leaving.style.transform = "";
        void leaving.offsetWidth;
        leaving.style.transition = "";
      }, 650);
      links[current].setAttribute("tabindex", "-1");
      tabs[current].classList.remove("is-active");
      tabs[current].removeAttribute("aria-current");
      current = next;
      links[current].removeAttribute("tabindex");
      tabs[current].classList.add("is-active");
      tabs[current].setAttribute("aria-current", "true");
      centerArrows();
    };
    const schedule = () => {
      clearTimeout(timer);
      const playing = !userPaused && !held && slides.length > 1;
      hc.classList.toggle("is-playing", playing);
      if (playing) timer = setTimeout(() => { show(current + 1); schedule(); }, DURATION);
    };
    tabs.forEach((dot, i) => dot.addEventListener("click", () => { if (i !== current) { show(i, i > current ? 1 : -1); schedule(); } }));
    const hold = (on) => { held = on; hc.classList.toggle("is-held", on); schedule(); };
    hc.addEventListener("mouseenter", () => hold(true));
    hc.addEventListener("mouseleave", () => hold(false));
    // Hold for keyboard focus only, so a mouse click on a tab doesn't stop rotation for good.
    hc.addEventListener("focusin", (e) => { if (e.target.matches(":focus-visible")) hold(true); });
    hc.addEventListener("focusout", () => hold(false));
    // Swipe left or right on the photo to change person (touch and pen; mice use the arrows).
    const stage = hc.querySelector(".hc__stage");
    let swipe = null;
    stage.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse") swipe = { x: e.clientX, y: e.clientY };
    });
    stage.addEventListener("pointerup", (e) => {
      if (!swipe) return;
      const dx = e.clientX - swipe.x, dy = e.clientY - swipe.y;
      swipe = null;
      if (slides.length > 1 && Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.5) {
        const step = dx < 0 ? 1 : -1;
        show(current + step, step);
        schedule();
      }
    });
    stage.addEventListener("pointercancel", () => (swipe = null));
    if (slides.length > 1) {
      hc.querySelector(".hc__dots").hidden = false;
      hc.querySelectorAll(".hc__nav").forEach((btn) => {
        btn.hidden = false;
        const step = btn.classList.contains("hc__nav--prev") ? -1 : 1;
        btn.addEventListener("click", () => { show(current + step, step); schedule(); });
      });
    }
    centerArrows();
    schedule();
  }

  /* ---------- Line the hero photo up with the text ----------
     On wide screens the photo's top meets the top of the headline and its bottom
     meets the bottom of the "Hosted by" logos; its width is 90% of its height. */
  const heroFig = document.querySelector(".hero__figure");
  const heroStage = heroFig && heroFig.querySelector(".hc__stage");
  if (heroStage) {
    const h1 = document.querySelector(".hero h1");
    const trust = document.querySelector(".hero__trust");
    const fit = () => {
      if (window.matchMedia("(max-width: 900px)").matches || !h1 || !trust) {
        heroFig.style.marginTop = heroFig.style.width = heroStage.style.height = heroStage.style.aspectRatio = "";
        return;
      }
      const cs = getComputedStyle(h1);
      const halfLeading = (parseFloat(cs.lineHeight) - parseFloat(cs.fontSize)) / 2;
      const top = h1.offsetTop + Math.max(0, halfLeading);
      const height = Math.max(300, trust.offsetTop + trust.offsetHeight - top);
      heroFig.style.marginTop = top + "px";
      heroFig.style.width = Math.round(height * 0.9) + "px";
      heroStage.style.aspectRatio = "auto";
      heroStage.style.height = height + "px";
    };
    fit();
    window.addEventListener("resize", fit);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  }

  /* ---------- Footer year ---------- */
  document.querySelectorAll("[data-year]").forEach((el) => (el.textContent = new Date().getFullYear()));

  /* ---------- Copy story link ---------- */
  document.querySelectorAll(".copy-link").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.url);
        button.textContent = "Link copied";
      } catch {
        window.prompt("Copy this link:", button.dataset.url);
      }
      setTimeout(() => (button.textContent = "Copy link"), 2500);
    });
  });

  /* ---------- Contact form ---------- */
  const form = document.getElementById("contact-form");
  if (!form) return;

  const email = form.dataset.email;
  const endpoint = form.dataset.endpoint;
  const select = form.querySelector("#subject");
  const status = document.getElementById("form-status");

  // contact.html?subject=donations pre-selects a subject.
  const wanted = new URLSearchParams(location.search).get("subject");
  if (wanted && [...select.options].some((o) => o.value === wanted)) select.value = wanted;

  // Show the donations or referral note only when that subject is chosen.
  const notes = [...document.querySelectorAll("[data-for]")];
  const showNotes = () => notes.forEach((n) => (n.hidden = n.dataset.for !== select.value));
  showNotes();
  select.addEventListener("change", showNotes);

  // Without a form service, the form hands the message to the visitor's email app; say so up front.
  if (!endpoint) {
    form.querySelector('button[type="submit"]').textContent = "Open in my email app";
    document.getElementById("form-hint").hidden = false;
  }

  const rules = {
    name: (v) => v.trim() !== "" || "Please enter your name.",
    email: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()) || "Please enter a valid email address.",
    subject: (v) => v !== "" || "Please choose a subject.",
    message: (v) => v.trim().length >= 5 || "Please write a short message.",
  };

  const check = (field) => {
    const result = rules[field.name](field.value);
    const wrap = field.closest(".field");
    const ok = result === true;
    wrap.classList.toggle("has-error", !ok);
    field.toggleAttribute("aria-invalid", !ok);
    wrap.querySelector(".field__error").textContent = ok ? "" : result;
    return ok;
  };

  const fields = [...form.elements].filter((f) => rules[f.name]);
  fields.forEach((f) => {
    f.addEventListener("blur", () => check(f));
    f.addEventListener("input", () => f.closest(".field").classList.contains("has-error") && check(f));
  });

  const say = (html, ok) => {
    status.className = "form-status is-visible " + (ok ? "form-status--ok" : "form-status--error");
    status.innerHTML = html;
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!fields.map(check).every(Boolean)) {
      form.querySelector(".has-error input, .has-error select, .has-error textarea").focus();
      return;
    }
    const data = Object.fromEntries(new FormData(form));
    const subject = select.options[select.selectedIndex].text;

    if (endpoint) {
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      try {
        const res = await fetch(endpoint, {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ ...data, subject }),
        });
        if (!res.ok) throw new Error(res.statusText);
        form.reset();
        say("Thank you. Your message has been sent, and we’ll be in touch soon.", true);
      } catch {
        say(`Sorry, your message didn’t go through. Please email us at <a href="mailto:${email}">${email}</a>.`, false);
      } finally {
        button.disabled = false;
      }
      return;
    }

    // No form service yet: open the visitor's email app with the message filled in.
    const body = `${data.message}\n\n${data.name}\n${data.email}`;
    location.href = `mailto:${email}?subject=${encodeURIComponent(`[${subject}] Message from ${data.name}`)}&body=${encodeURIComponent(body)}`;
    say(`If your email app didn’t open, copy your message and send it to <a href="mailto:${email}">${email}</a>. Nothing has been sent yet.`, true);
  });
})();
