/* "Where that ranks in New York" for divinedavis.com.
 *
 * Reads nycrank.json (regenerated on the droplet daily, see
 * tools/update_nycrank.py). Same contract as loc.js and github-activity.js:
 * every number is already in index.html as a last-known value, and this file
 * only ever replaces it with a fresher one, so JS off or a 404 leaves the
 * section reading correctly instead of empty.
 *
 * The headline percentile and the median both come from cohorts[0] — the widest
 * cohort the generator publishes, every New York account that committed at all
 * in the window. The generator still computes and ships the narrower cohorts;
 * the page just doesn't draw them.
 *
 * No count-up animation. These numbers move by fractions of a percent a day, so
 * easing them in would be motion invented for its own sake. */
(function () {
  var SRC = 'nycrank.json';
  var REFRESH_MS = 30 * 60 * 1000;     // the file itself changes once a day

  var root = document.getElementById('nyc-rank');
  if (!root) return;

  var stampEl = root.querySelector('[data-nyc-stamp]');

  function comma(n) { return Math.round(n).toLocaleString('en-US'); }

  /* 98.1 -> "Top 2%". Ceil so the claim is never better than the measurement:
     98.1st percentile is top 1.9%, and rounding that to "top 1%" would be a
     nicer number and a false one. */
  function topPct(p) {
    var rest = 100 - p;
    return 'Top ' + (rest < 1 ? rest.toFixed(1) : Math.ceil(rest)) + '%';
  }

  function setText(sel, text) {
    var node = root.querySelector(sel);
    if (node && text != null) node.textContent = text;
  }

  function render(d) {
    var head = (d.cohorts && d.cohorts[0]) || {};

    setText('[data-nyc-stat="top_pct"]', topPct(d.percentile));
    setText('[data-nyc-stat="commits"]', comma(d.commits));
    setText('[data-nyc-stat="active_days"]', comma(d.active_days));
    setText('[data-nyc-days-note]', 'of ' + comma(d.window_span) + ' days');
    setText('[data-nyc-stat="above"]', comma(d.above));
    setText('[data-nyc-stat="median"]', comma(head.median));

    if (stampEl && d.updated) {
      stampEl.textContent = 'Measured ' + new Date(d.updated)
        .toLocaleString('en-US', { month: 'short', day: 'numeric',
                                   hour: 'numeric', minute: '2-digit' });
      stampEl.setAttribute('datetime', d.updated);
    }
  }

  function load(first) {
    fetch(SRC + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (json) {
        if (!json || !json.commits || !json.cohorts) throw new Error('empty');
        if (first) root.classList.add('is-live');
        render(json);
      })
      .catch(function () {
        // Without .is-live the section keeps the numbers baked into the HTML,
        // which are the last ones known to be good.
      });
  }

  load(true);
  setInterval(function () { if (!document.hidden) load(false); }, REFRESH_MS);
})();
