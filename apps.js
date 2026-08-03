/* Shipped-apps inventory for divinedavis.com.
 *
 * Reads apps.json (regenerated on the droplet every 15 minutes, see
 * tools/update_apps.py) and rebuilds both lists plus the four counts.
 *
 * These numbers move on the scale of weeks, not minutes, so unlike the
 * lines-of-code counter nothing here animates and nothing polls on a timer —
 * one fetch on load is the whole behaviour. A number that changes twice a month
 * does not need a heartbeat.
 *
 * No-JS and offline visitors keep the lists baked into index.html; this script
 * only ever replaces them with fresher ones. */
(function () {
  var SRC = 'apps.json';

  var root = document.getElementById('apps');
  if (!root) return;

  var iosList = root.querySelector('[data-apps-ios]');
  var webList = root.querySelector('[data-apps-web]');
  var stampEl = root.querySelector('[data-apps-stamp]');

  function comma(n) { return n.toLocaleString('en-US'); }

  function row(label, href, tagText, tagClass) {
    var li = document.createElement('li');

    var name;
    if (href) {
      name = document.createElement('a');
      name.href = href;
      name.target = '_blank';
      name.rel = 'noopener';
    } else {
      name = document.createElement('span');
    }
    name.textContent = label;

    var tag = document.createElement('span');
    tag.className = tagClass;
    tag.textContent = tagText;

    li.appendChild(name);
    li.appendChild(tag);
    return li;
  }

  function render(data) {
    root.querySelectorAll('[data-apps-stat]').forEach(function (node) {
      var key = node.getAttribute('data-apps-stat');
      if (typeof data[key] === 'number') node.textContent = comma(data[key]);
    });

    if (iosList && data.ios && data.ios.length) {
      iosList.textContent = '';
      data.ios.forEach(function (a) {
        var beta = a.status !== 'App Store';
        iosList.appendChild(row(
          a.name, a.url || null, a.status,
          'apps-chip' + (beta ? ' is-beta' : '')
        ));
      });
    }

    if (webList && data.web && data.web.length) {
      webList.textContent = '';
      data.web.forEach(function (w) {
        webList.appendChild(row(
          w.name, 'https://' + w.domain, w.domain, 'apps-host'
        ));
      });
    }

    if (stampEl && data.updated) {
      stampEl.textContent = 'Checked ' + new Date(data.updated)
        .toLocaleString('en-US', { month: 'short', day: 'numeric',
                                   hour: 'numeric', minute: '2-digit' });
      stampEl.setAttribute('datetime', data.updated);
    }
    root.classList.add('is-live');
  }

  fetch(SRC + '?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
    .then(function (json) {
      if (!json || !json.ios_total) throw new Error('empty');
      render(json);
    })
    .catch(function () {
      // Without .is-live the section keeps the lists baked into the HTML,
      // which are the last ones known to be good.
    });
})();
