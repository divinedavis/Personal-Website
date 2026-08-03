/* Lines-of-code counter for divinedavis.com.
 *
 * Reads loc.json (regenerated on the droplet every 5 minutes, see
 * tools/update_loc.py) and keeps the headline honest between page loads.
 *
 * The first paint sets the number flat and later refreshes animate the delta.
 * That is deliberate: counting up from zero to half a million on every load is
 * a slot machine, but rolling +214 when a push lands while the tab is open is
 * the whole point of the thing being live.
 *
 * Languages are ranked bars in one hue rather than a stacked bar in eight —
 * the job is comparing magnitudes, and a single series needs no legend or
 * categorical palette. Widths are relative to the largest language, so Python
 * is always the full track and everything else reads against it.
 *
 * No-JS and offline visitors keep the numbers baked into index.html; this
 * script only ever replaces them with fresher ones. */
(function () {
  var SRC = 'loc.json';
  var REFRESH_MS = 60000;       // the file itself only changes every 5 min

  var root = document.getElementById('loc');
  if (!root) return;

  var langWrap = root.querySelector('[data-loc-langs]');
  var stampEl = root.querySelector('[data-loc-stamp]');
  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  var counters = {};            // stat key -> last value we rendered
  var data = null;

  function comma(n) { return n.toLocaleString('en-US'); }

  function setStat(node, value) {
    if (!node) return;
    var key = node.getAttribute('data-loc-stat');
    var from = counters[key];
    counters[key] = value;

    // from == null is the first paint over the baked-in fallback: no animation,
    // or the page opens by spinning a five-digit odometer at the reader.
    if (reduceMotion || from == null || from === value) {
      node.textContent = comma(value);
      return;
    }
    var t0 = performance.now();
    var dur = Math.min(1200, 300 + Math.abs(value - from) * 4);

    (function step(now) {
      var p = Math.min(1, (now - t0) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      node.textContent = comma(Math.round(from + (value - from) * eased));
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }

  function renderStats() {
    root.querySelectorAll('[data-loc-stat]').forEach(function (node) {
      var key = node.getAttribute('data-loc-stat');
      if (data[key] != null) setStat(node, data[key]);
    });

    var top = data.languages && data.languages[0];
    var lead = root.querySelector('[data-loc-lead]');
    var leadNote = root.querySelector('[data-loc-lead-note]');
    if (top && lead) lead.textContent = top.name;
    if (top && leadNote) leadNote.textContent = comma(top.lines) + ' lines';

    if (stampEl && data.updated) {
      stampEl.textContent = 'Updated ' + new Date(data.updated)
        .toLocaleString('en-US', { month: 'short', day: 'numeric',
                                   hour: 'numeric', minute: '2-digit' });
      stampEl.setAttribute('datetime', data.updated);
    }
  }

  function renderLangs() {
    if (!langWrap || !data.languages || !data.languages.length) return;
    var max = data.languages.reduce(function (m, l) {
      return Math.max(m, l.lines);
    }, 0);
    if (!max) return;

    langWrap.textContent = '';
    data.languages.forEach(function (l, i) {
      var row = document.createElement('div');
      row.className = 'loc-row' + (i === 0 ? ' is-max' : '');

      var name = document.createElement('span');
      name.className = 'loc-lang';
      name.textContent = l.name;

      var track = document.createElement('span');
      track.className = 'loc-track';
      var fill = document.createElement('span');
      fill.className = 'loc-fill';
      fill.style.width = (l.lines / max * 100).toFixed(1) + '%';
      track.appendChild(fill);

      var val = document.createElement('span');
      val.className = 'loc-val';
      val.textContent = comma(l.lines);

      row.appendChild(name);
      row.appendChild(track);
      row.appendChild(val);
      langWrap.appendChild(row);
    });
  }

  function load(first) {
    fetch(SRC + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (json) {
        if (!json || !json.added) throw new Error('empty');
        data = json;
        if (first) root.classList.add('is-live');
        renderStats();
        renderLangs();
      })
      .catch(function () {
        // Nothing to do: without .is-live the section keeps the numbers baked
        // into the HTML, which are the last ones known to be good.
      });
  }

  load(true);
  setInterval(function () { if (!document.hidden) load(false); }, REFRESH_MS);
})();
