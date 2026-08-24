/* "Where that ranks in New York" for divinedavis.com.
 *
 * Reads nycrank.json (regenerated on the droplet daily, see
 * tools/update_nycrank.py). Same contract as loc.js and github-activity.js:
 * every number is already in index.html as a last-known value, and this file
 * only ever replaces it with a fresher one, so JS off or a 404 leaves the
 * section reading correctly instead of empty.
 *
 * The ladder is four percentile bars in one hue, not four numbers, because the
 * point is that the rank falls as the bar for inclusion rises — a single "top
 * 2%" on its own is the least interesting true thing here. Percentile bars get
 * a visible track: unlike the magnitude bars elsewhere on the page, these are
 * fractions of a fixed 100, and a bar with no 0-100 reference can't show that.
 *
 * No animation on the fills. The numbers move by fractions of a percent a day;
 * easing them in would be motion invented for its own sake. */
(function () {
  var SRC = 'nycrank.json';
  var REFRESH_MS = 30 * 60 * 1000;     // the file itself changes once a day

  var root = document.getElementById('nyc-rank');
  if (!root) return;

  var rowsWrap = root.querySelector('[data-nyc-rows]');
  var stampEl = root.querySelector('[data-nyc-stamp]');

  function comma(n) { return Math.round(n).toLocaleString('en-US'); }

  function ordinal(n) {
    var r = Math.round(n);
    if (r % 100 >= 11 && r % 100 <= 13) return r + 'th';
    return r + (['th', 'st', 'nd', 'rd'][r % 10] || 'th');
  }

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
    setText('[data-nyc-pop]', comma(d.population));
    setText('[data-nyc-frame-pop]', comma(d.frame_population));
    setText('[data-nyc-sample]', comma(d.sample_n));

    if (rowsWrap && d.cohorts && d.cohorts.length) {
      rowsWrap.textContent = '';
      var best = d.cohorts.reduce(function (m, c) {
        return Math.max(m, c.percentile);
      }, 0);

      d.cohorts.forEach(function (c) {
        var row = document.createElement('div');
        row.className = 'nyc-row' + (c.percentile === best ? ' is-max' : '');

        var name = document.createElement('span');
        name.className = 'nyc-label';
        // textContent, not innerHTML: the labels are plain sentences with a
        // literal em dash, so there is nothing to gain from parsing them as
        // markup and no reason to leave that door open in a file whose input
        // arrives over the network.
        name.textContent = String(c.label);

        var track = document.createElement('span');
        track.className = 'nyc-track';
        var fill = document.createElement('span');
        fill.className = 'nyc-fill';
        fill.style.width = Math.max(0, Math.min(100, c.percentile)) + '%';
        track.appendChild(fill);

        var val = document.createElement('span');
        val.className = 'nyc-val';
        val.textContent = ordinal(c.percentile);

        var pop = document.createElement('span');
        pop.className = 'nyc-pop';
        pop.textContent = comma(c.population) + ' people';

        row.appendChild(name);
        row.appendChild(track);
        row.appendChild(val);
        row.appendChild(pop);
        rowsWrap.appendChild(row);
      });
    }

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
