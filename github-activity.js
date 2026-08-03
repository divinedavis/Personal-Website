/* GitHub contribution activity for divinedavis.com.
 *
 * Reads github.json (refreshed on the droplet every 30 minutes, see
 * tools/update_github.py) and draws daily contributions as columns, with a
 * headline total that counts up to the same number the GitHub profile shows.
 *
 * Why columns rather than GitHub's 7x53 heatmap: a heatmap bins into five
 * shades, so a 3-contribution day and a 60-contribution day can land in the same
 * bucket. Height is a continuous channel, so the shape of a year reads honestly.
 *
 * Geometry is measured from the container in real pixels and redrawn on resize
 * rather than scaled with a viewBox — stretching the SVG would distort the
 * rounded bar caps and the 2px gaps that keep neighbouring days distinct.
 *
 * No-JS and offline visitors keep the numbers baked into index.html; this script
 * only ever replaces them with fresher ones. */
(function () {
  var SRC = 'github.json';
  var REFRESH_MS = 90000;      // the file itself only changes every 30 min
  var MAX_BAR = 24;            // never fill the slot; the leftover is air
  var GAP = 2;                 // surface gap — what separates touching bars
  var PLOT_H = 132;
  var AXIS_H = 20;
  var PAD_L = 34;              // room for the y-tick labels
  var PAD_R = 4;

  var RANGES = [
    { id: '30d',  label: '30 days',  days: 30,  bucket: 'day' },
    { id: '90d',  label: '90 days',  days: 90,  bucket: 'day' },
    { id: '1y',   label: '1 year',   days: 365, bucket: 'week' },
    { id: 'all',  label: 'All',      days: 0,   bucket: 'month' }
  ];

  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var SVG_NS = 'http://www.w3.org/2000/svg';

  // Sunday-indexed to match Date#getUTCDay; the rhythm block reads them out
  // Monday-first so the weekend lands together at the end.
  var DOW = ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
             'Thursday', 'Friday', 'Saturday'];
  var DOW_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var WEEK_ORDER = [1, 2, 3, 4, 5, 6, 0];
  var WEEKS_BACK = 52;

  var root = document.getElementById('gh-activity');
  if (!root) return;

  var plot = root.querySelector('[data-gh-plot]');
  var tipEl = root.querySelector('[data-gh-tip]');
  var tableWrap = root.querySelector('[data-gh-table]');
  var tableBtn = root.querySelector('[data-gh-table-toggle]');
  // The weekly rhythm sits outside #gh-activity — it shares a row with the
  // lines-of-code section — but it is still drawn from this file's data, so it
  // is looked up against the document rather than the section.
  var weekRows = document.querySelector('[data-gh-week]');
  var weekLede = document.querySelector('[data-gh-week-lede]');
  var stampEl = root.querySelector('[data-gh-stamp]');
  var rangeRow = root.querySelector('[data-gh-ranges]');

  var data = null;
  var range = RANGES[1];
  var counters = {};           // stat key -> last value we animated to
  var lastBucket = 'day';      // what the current render actually drew
  var redrawTimer = null;

  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(tag, attrs, text) {
    var n = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }

  function comma(n) { return n.toLocaleString('en-US'); }

  function dayLabel(iso) {
    var p = iso.split('-');
    return MONTHS[+p[1] - 1] + ' ' + +p[2] + ', ' + p[0];
  }

  function plural(n, word) { return comma(n) + ' ' + word + (n === 1 ? '' : 's'); }

  /* ---- stats ------------------------------------------------------------ */

  /* The headline is a live counter, so it animates to whatever the file now says
     — including on a refresh that only moves it by one. */
  function setStat(node, value, format) {
    if (!node) return;
    var key = node.getAttribute('data-gh-stat');
    var from = counters[key];
    counters[key] = value;

    if (reduceMotion || from === value || from == null && value > 5000) {
      node.textContent = format(value);
      return;
    }
    var start = from == null ? 0 : from;
    var t0 = performance.now();
    var dur = Math.min(900, 200 + Math.abs(value - start) * 6);

    (function step(now) {
      var p = Math.min(1, (now - t0) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      node.textContent = format(Math.round(start + (value - start) * eased));
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }

  function renderStats() {
    root.querySelectorAll('[data-gh-stat]').forEach(function (node) {
      var key = node.getAttribute('data-gh-stat');
      if (key === 'best_day') {
        setStat(node, data.best_day.count, comma);
        var when = root.querySelector('[data-gh-best-date]');
        if (when) when.textContent = 'on ' + dayLabel(data.best_day.date);
      } else if (data[key] != null) {
        setStat(node, data[key], comma);
      }
    });
    if (stampEl) {
      stampEl.textContent = 'Updated ' + new Date(data.updated)
        .toLocaleString('en-US', { month: 'short', day: 'numeric',
                                   hour: 'numeric', minute: '2-digit' });
      stampEl.setAttribute('datetime', data.updated);
    }
  }

  /* ---- series ----------------------------------------------------------- */

  function days() {
    var start = new Date(data.start + 'T00:00:00');
    return data.counts.map(function (count, i) {
      var d = new Date(start.getTime() + i * 86400000);
      return { date: d, iso: d.toISOString().slice(0, 10), count: count };
    });
  }

  /* Weekly buckets for the long ranges: a year of daily columns would be under
     2px wide apiece, which no gap or rounded cap survives. */
  function series(bucket) {
    var all = days();
    var slice = range.days ? all.slice(Math.max(0, all.length - range.days)) : all;
    if (bucket === 'day') {
      return slice.map(function (d) {
        return { key: d.iso, count: d.count, date: d.date,
                 label: dayLabel(d.iso), sub: plural(d.count, 'contribution') };
      });
    }

    var groups = [], cur = null;
    slice.forEach(function (d) {
      var fresh = bucket === 'month'
        ? !cur || d.date.getDate() === 1
        : !cur || d.date.getDay() === 0;
      if (fresh) {
        cur = { key: d.iso, count: 0, date: d.date };
        groups.push(cur);
      }
      cur.count += d.count;
    });
    return groups.map(function (g) {
      g.label = bucket === 'month'
        ? MONTHS[g.date.getMonth()] + ' ' + g.date.getFullYear()
        : 'Week of ' + dayLabel(g.key);
      g.sub = plural(g.count, 'contribution');
      return g;
    });
  }

  /* ---- chart ------------------------------------------------------------ */

  /* Ticks land on round numbers so they can carry the values no bar is labelled
     with. */
  function niceMax(max) {
    if (max <= 5) return 5;
    var mag = Math.pow(10, Math.floor(Math.log10(max)));
    return Math.ceil(max / (mag / 2)) * (mag / 2);
  }

  /* Which bucket actually fits. A phone showing 90 days has ~4px per column, and
     a 4px slot minus the 2px gap is a 2px hairline — so the chart steps up to
     weeks rather than drawing days too thin to read. The table caption and the
     tooltips follow, so nothing claims to be daily when it isn't. */
  function bucketFor(width) {
    if (range.bucket !== 'day') return range.bucket;
    var perDay = (width - PAD_L - PAD_R) / range.days;
    return perDay < GAP + 3 ? 'week' : 'day';
  }

  function draw() {
    var width = Math.max(260, plot.clientWidth);
    var bucket = bucketFor(width);
    var pts = series(bucket);
    if (!pts.length) return;

    var height = PLOT_H + AXIS_H;
    var inner = width - PAD_L - PAD_R;
    var slot = inner / pts.length;
    var barW = Math.max(1, Math.min(MAX_BAR, slot - GAP));
    var top = niceMax(Math.max.apply(null, pts.map(function (p) { return p.count; })));

    lastBucket = bucket;

    var svg = el('svg', {
      width: width, height: height, viewBox: '0 0 ' + width + ' ' + height,
      class: 'gh-svg', role: 'img',
      'aria-label': range.label + ' of GitHub contributions, ' +
        'one column per ' + bucket +
        '. Peak ' + comma(top) + '. The table below lists every value.'
    });

    // Gridlines: solid hairlines one step off the surface, behind the data.
    [top, top / 2].forEach(function (v) {
      var y = PLOT_H - (v / top) * PLOT_H;
      svg.appendChild(el('line', { x1: PAD_L, x2: width - PAD_R, y1: y, y2: y,
                                   class: 'gh-grid' }));
      svg.appendChild(el('text', { x: PAD_L - 6, y: y + 4, class: 'gh-tick' },
                         comma(v)));
    });
    svg.appendChild(el('line', { x1: PAD_L, x2: width - PAD_R,
                                 y1: PLOT_H, y2: PLOT_H, class: 'gh-axis' }));

    var bars = el('g', {});
    var hits = el('g', {});
    var byYear = (pts[pts.length - 1].date - pts[0].date) / 86400000 > 550;
    var lastUnit = null;

    pts.forEach(function (p, i) {
      var x = PAD_L + i * slot + (slot - barW) / 2;
      var h = top ? (p.count / top) * PLOT_H : 0;

      if (h > 0) {
        // Rounded data-end, square at the baseline: draw the cap by hand rather
        // than with rx, which would round the foot off the axis too.
        var r = Math.min(4, barW / 2, h);
        bars.appendChild(el('path', {
          class: 'gh-bar',
          d: 'M' + x + ' ' + PLOT_H +
             'V' + (PLOT_H - h + r) +
             'a' + r + ' ' + r + ' 0 0 1 ' + r + ' ' + -r +
             'h' + (barW - 2 * r) +
             'a' + r + ' ' + r + ' 0 0 1 ' + r + ' ' + r +
             'V' + PLOT_H + 'Z'
        }));
      }

      // Full-height column as the hit target — the bars themselves are far too
      // thin to land on, and a zero day has no bar at all.
      var hit = el('rect', {
        x: PAD_L + i * slot, y: 0, width: slot, height: PLOT_H,
        class: 'gh-hit', tabindex: 0, role: 'button',
        'aria-label': p.label + ': ' + p.sub
      });
      hit.addEventListener('mouseenter', function () { showTip(p, hit, h); });
      hit.addEventListener('focus', function () { showTip(p, hit, h); });
      hit.addEventListener('mouseleave', hideTip);
      hit.addEventListener('blur', hideTip);
      hits.appendChild(hit);

      // Month names over a multi-year span repeat and read ambiguously, so past
      // a year and a half the axis switches to years. One label per unit, at the
      // first column in it, and never so close to the right edge that it would
      // run past the plot.
      var unit = byYear ? p.date.getFullYear() : p.date.getMonth();
      if (unit !== lastUnit) {
        lastUnit = unit;
        if (i < pts.length - 2) {
          svg.appendChild(el('text', {
            x: PAD_L + i * slot, y: PLOT_H + 15, class: 'gh-month'
          }, byYear ? unit : MONTHS[unit]));
        }
      }
    });

    svg.appendChild(bars);
    svg.appendChild(hits);

    // Replace only the previous chart — the tooltip lives in this container too
    // and must survive a redraw.
    var prev = plot.querySelector('svg');
    if (prev) prev.remove();
    plot.appendChild(svg);
    plot.classList.remove('is-stale');
  }

  function showTip(p, target, barH) {
    if (!tipEl) return;
    var box = target.getBoundingClientRect();
    var host = plot.getBoundingClientRect();
    tipEl.textContent = '';
    var strong = document.createElement('strong');
    strong.textContent = p.sub;
    var span = document.createElement('span');
    span.textContent = p.label;
    tipEl.appendChild(strong);
    tipEl.appendChild(span);
    tipEl.hidden = false;   // has to be laid out before it can be measured

    // Ride just above the column, but stay inside the plot — floating above the
    // container would land the tip on top of the controls row.
    var x = box.left - host.left + box.width / 2;
    var half = tipEl.offsetWidth / 2;
    var y = Math.max(0, PLOT_H - barH - tipEl.offsetHeight - 6);
    tipEl.style.left = Math.max(half, Math.min(host.width - half, x)) + 'px';
    tipEl.style.top = y + 'px';
    tipEl.classList.add('is-on');
  }

  function hideTip() {
    if (!tipEl) return;
    tipEl.classList.remove('is-on');
    tipEl.hidden = true;
  }

  /* ---- table twin ------------------------------------------------------- */

  function renderTable() {
    if (!tableWrap) return;
    var pts = series(lastBucket).slice().reverse();
    var rows = pts.map(function (p) {
      return '<tr><th scope="row">' + p.label + '</th><td>' + comma(p.count) + '</td></tr>';
    }).join('');
    tableWrap.innerHTML =
      '<table class="gh-table"><caption>Contributions per ' + lastBucket + ', ' +
      range.label.toLowerCase() + ', most recent first</caption>' +
      '<thead><tr><th scope="col">' +
      (lastBucket === 'day' ? 'Day' : lastBucket === 'week' ? 'Week of' : 'Month') +
      '</th><th scope="col">Contributions</th></tr></thead><tbody>' +
      rows + '</tbody></table>';
  }

  /* ---- weekly rhythm ----------------------------------------------------- */

  /* Average contributions per weekday over the last 52 weeks.
   *
   * Averages, not totals, because the window has to divide evenly: 364 days is
   * exactly 52 of each weekday, so no bar is taller merely for having had more
   * chances. Today is excluded — a day that's still in progress would drag its
   * own weekday down every morning.
   *
   * The weekday comes from index arithmetic off data.start rather than from a
   * Date, since the day objects are built by adding 86,400,000ms and a DST
   * boundary shifts one of them back an hour into the previous day. */
  function weekAverages() {
    var counts = data.counts;
    var end = counts.length - 1;              // index of today
    if (end < 7) return null;
    var from = Math.max(0, end - WEEKS_BACK * 7);
    var startDow = new Date(data.start + 'T00:00:00Z').getUTCDay();

    var total = [0, 0, 0, 0, 0, 0, 0];
    var seen = [0, 0, 0, 0, 0, 0, 0];
    for (var i = from; i < end; i++) {
      var d = (startDow + i) % 7;
      total[d] += counts[i];
      seen[d] += 1;
    }
    return WEEK_ORDER.map(function (d) {
      return { dow: d, total: total[d], days: seen[d],
               avg: seen[d] ? total[d] / seen[d] : 0 };
    });
  }

  function renderWeek() {
    if (!weekRows) return;
    var rows = weekAverages();
    if (!rows) return;

    var peak = rows.reduce(function (a, b) { return b.avg > a.avg ? b : a; });
    var low = rows.reduce(function (a, b) { return b.avg < a.avg ? b : a; });
    var top = peak.avg || 1;

    weekRows.textContent = '';
    rows.forEach(function (r) {
      var one = r.avg.toFixed(1);
      var row = document.createElement('div');
      row.className = 'gh-week-row' + (r === peak ? ' is-max' : '');
      // Every value is printed at the end of its own bar, so there is nothing a
      // tooltip would add — the title only carries the sample it came from.
      row.title = DOW[r.dow] + ': ' + one + ' a day on average, ' +
                  comma(r.total) + ' across ' + r.days + ' of them';

      var day = document.createElement('span');
      day.className = 'gh-week-day';
      day.textContent = DOW_SHORT[r.dow];

      var track = document.createElement('span');
      track.className = 'gh-week-track';
      var fill = document.createElement('span');
      fill.className = 'gh-week-fill';
      fill.style.width = Math.max(1, (r.avg / top) * 100) + '%';
      track.appendChild(fill);

      var val = document.createElement('span');
      val.className = 'gh-week-val';
      val.textContent = one;

      row.appendChild(day);
      row.appendChild(track);
      row.appendChild(val);
      weekRows.appendChild(row);
    });

    if (weekLede) {
      weekLede.textContent = DOW[peak.dow] + ' is my busiest day — ' +
        peak.avg.toFixed(1) + ' contributions a day on average, against ' +
        low.avg.toFixed(1) + ' on ' + DOW[low.dow] + '.';
    }
  }

  /* ---- wiring ----------------------------------------------------------- */

  function renderAll() {
    renderStats();
    renderWeek();
    draw();
    if (tableWrap && !tableWrap.hidden) renderTable();
  }

  function buildRanges() {
    if (!rangeRow) return;
    RANGES.forEach(function (r) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'gh-range' + (r.id === range.id ? ' is-on' : '');
      b.textContent = r.label;
      b.setAttribute('aria-pressed', r.id === range.id ? 'true' : 'false');
      b.addEventListener('click', function () {
        range = r;
        rangeRow.querySelectorAll('.gh-range').forEach(function (o) {
          o.classList.toggle('is-on', o === b);
          o.setAttribute('aria-pressed', o === b ? 'true' : 'false');
        });
        hideTip();
        draw();
        if (tableWrap && !tableWrap.hidden) renderTable();
      });
      rangeRow.appendChild(b);
    });
  }

  function load(first) {
    // Hold the previous render at reduced opacity instead of flashing a
    // skeleton — the chart is already correct, just a few minutes old.
    if (!first) plot.classList.add('is-stale');
    fetch(SRC + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (json) {
        if (!json || !json.counts || !json.counts.length) throw new Error('empty');
        data = json;
        if (first) {
          root.classList.add('is-live');
          buildRanges();
        }
        renderAll();
      })
      .catch(function () {
        // Nothing to do on a failed refresh: without .is-live the section keeps
        // the numbers baked into the HTML, and a stale chart stays up.
        plot.classList.remove('is-stale');
      });
  }

  if (tableBtn) {
    tableBtn.addEventListener('click', function () {
      var open = tableWrap.hidden;
      tableWrap.hidden = !open;
      tableBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      tableBtn.textContent = open ? 'Hide the numbers' : 'Show the numbers';
      if (open) renderTable();
    });
  }

  // A resize can change which bucket fits, so the table has to follow the chart.
  window.addEventListener('resize', function () {
    clearTimeout(redrawTimer);
    redrawTimer = setTimeout(function () {
      if (!data) return;
      hideTip();
      draw();
      if (tableWrap && !tableWrap.hidden) renderTable();
    }, 120);
  });

  // A theme flip changes the surface colour the gaps are cut out of.
  new MutationObserver(function () { if (data) draw(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  load(true);
  setInterval(function () { if (!document.hidden) load(false); }, REFRESH_MS);
})();
