/* divinedavis.com home: menu toggle, hero crossfade, Brooklyn clock, and
   wheel-to-sideways scrolling on the project strips. */
(function () {
  var bar = document.querySelector('[data-bar]');
  var burger = document.querySelector('[data-burger]');
  var menu = document.querySelector('[data-menu]');

  function setOpen(open) {
    bar.classList.toggle('is-open', open);
    menu.hidden = !open;
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  }
  burger.addEventListener('click', function () { setOpen(menu.hidden); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !menu.hidden) { setOpen(false); burger.focus(); }
  });
  document.addEventListener('click', function (e) {
    if (!menu.hidden && !bar.contains(e.target)) setOpen(false);
  });

  // The bar's tagline follows the section under it, like a running header.
  var tag = document.querySelector('[data-bar-tag]');
  var work = document.getElementById('work');
  function retag() {
    tag.textContent = work.getBoundingClientRect().top < 80 ? 'Selected work' : 'Built in Brooklyn';
  }
  window.addEventListener('scroll', retag, { passive: true });
  retag();

  // Local time in Brooklyn inside the menu.
  var clock = document.querySelector('[data-clock]');
  function tick() {
    try {
      clock.textContent = new Date().toLocaleTimeString('en-US', {
        timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit'
      }) + ' ET';
    } catch (e) { clock.textContent = 'ET'; }
  }
  tick();
  setInterval(tick, 30000);

  // Hero crossfade. Skipped for reduced motion, which keeps the first frame.
  var slides = document.querySelectorAll('.hero-bg img');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (slides.length > 1 && !reduce) {
    var i = 0;
    setInterval(function () {
      if (document.hidden) return;
      slides[i].classList.remove('is-on');
      i = (i + 1) % slides.length;
      slides[i].classList.add('is-on');
    }, 5000);
  }

  // A vertical wheel over a strip scrolls it sideways until it hits an end,
  // then lets the page carry on scrolling.
  document.querySelectorAll('[data-strip]').forEach(function (strip) {
    strip.addEventListener('wheel', function (e) {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      var max = strip.scrollWidth - strip.clientWidth;
      if (max <= 0) return;
      var atStart = strip.scrollLeft <= 0 && e.deltaY < 0;
      var atEnd = strip.scrollLeft >= max - 1 && e.deltaY > 0;
      if (atStart || atEnd) return;
      e.preventDefault();
      strip.scrollLeft += e.deltaY;
    }, { passive: false });
  });
})();
