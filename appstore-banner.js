/* "Get the iPhone app" banner for the web pages of an app that is (or is
 * about to be) on the App Store.
 *
 * Self-activating: the page declares the App Store id and the script asks the
 * public iTunes lookup whether that id is live. Nothing shows until Apple
 * returns a result, so this can ship before the app is approved and starts
 * working the moment the listing goes up — no redeploy. Off the App Store
 * again (pulled, expired agreement) and it disappears the same way.
 *
 * Shown only on iPhone and iPad, in any browser (Safari's own Smart App Banner
 * is Safari-only and invisible inside Chrome, Gmail, Instagram etc.), and
 * dismissable — a viewer who taps ✕ is left alone for 30 days.
 *
 * Markup:  <div data-appstore-banner="6792398287" data-app-name="Spendcap"></div>
 *          <script src="/appstore-banner.js" defer></script>
 * The container sits at the very top of <body>; it stays empty on every
 * other device, so it costs the page nothing. */
(function () {
  var host = document.querySelector('[data-appstore-banner]');
  if (!host) return;

  var id = (host.getAttribute('data-appstore-banner') || '').replace(/\D/g, '');
  var name = host.getAttribute('data-app-name') || 'the app';
  if (!id) return;

  var ua = navigator.userAgent || '';
  var ios = /iPhone|iPad|iPod/.test(ua) ||
            (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); // iPadOS
  if (!ios) return;

  var KEY = 'appstore-banner-dismissed-' + id;
  try {
    var until = parseInt(localStorage.getItem(KEY) || '0', 10);
    if (until && Date.now() < until) return;
  } catch (e) { /* private mode: show it, it's just a banner */ }

  fetch('https://itunes.apple.com/lookup?id=' + id + '&country=us')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      var app = d && d.results && d.results[0];
      // Only ever link into Apple's own store, whatever the response says.
      if (!app || !/^https:\/\/apps\.apple\.com\//.test(app.trackViewUrl || '')) return;
      render(app);
    })
    .catch(function () { /* offline or blocked: no banner, no harm */ });

  function render(app) {
    var bar = document.createElement('div');
    bar.className = 'appstore-banner';
    bar.setAttribute('role', 'complementary');
    bar.setAttribute('aria-label', 'Get the ' + name + ' iPhone app');

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'appstore-banner-close';
    close.setAttribute('aria-label', 'Dismiss');
    close.textContent = '×';
    close.addEventListener('click', function () {
      try { localStorage.setItem(KEY, String(Date.now() + 30 * 864e5)); } catch (e) {}
      bar.remove();
    });

    var icon = document.createElement('img');
    icon.className = 'appstore-banner-icon';
    icon.src = app.artworkUrl100 || app.artworkUrl60 || '';
    icon.alt = '';
    icon.width = 44; icon.height = 44;

    var text = document.createElement('div');
    text.className = 'appstore-banner-text';
    var title = document.createElement('strong');
    title.textContent = app.trackName || name;
    var sub = document.createElement('span');
    sub.textContent = app.price === 0 || app.formattedPrice === 'Free'
      ? 'Free on the App Store' : 'On the App Store';
    text.appendChild(title);
    text.appendChild(sub);

    var cta = document.createElement('a');
    cta.className = 'appstore-banner-cta';
    cta.href = app.trackViewUrl;
    cta.rel = 'noopener';
    cta.textContent = 'Get';

    bar.appendChild(close);
    bar.appendChild(icon);
    bar.appendChild(text);
    bar.appendChild(cta);
    host.appendChild(bar);
    host.classList.add('is-live');
  }
})();
