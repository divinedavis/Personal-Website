#!/usr/bin/env python3
"""Publish divinedavis.com's GitHub contribution numbers as github.json.

GitHub has no public JSON for a contribution calendar, but the fragment that
renders the grid on a profile page — https://github.com/users/<login>/contributions
— is public HTML, needs no token, and accepts ?from=&to= to page back through
earlier years. Scraping that beats the GraphQL API here for one reason: there is
no secret to keep on the droplet. The trade is that a GitHub markup change breaks
parsing, so the script refuses to overwrite a good github.json with a bad one
(see `guard` at the bottom).

Counts are public contributions only, which is exactly what a visitor to the
profile would see.

Layout of the output is a dense array, not a list of {date, count} objects:
`counts[i]` is the day `start + i`, so a three-year window is ~4KB of JSON
instead of ~60KB.

Runs from cron on 167.71.170.219 and scp's the result to the web host (159).
"""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

USER = "divinedavis"
YEARS_BACK = 2          # this calendar year plus the two before it
OUT = "/root/portfolio-stats/github.json"
DEST = "root@159.203.110.79:/var/www/divinedavis/github.json"

# GitHub 403s the default urllib agent.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DAY_RE = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="([^"]+)"')
TIP_RE = re.compile(r'<tool-tip[^>]*for="([^"]+)"[^>]*>(.*?)</tool-tip>', re.S)
COUNT_RE = re.compile(r"^\s*(\d[\d,]*)\s+contribution")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def scrape(from_date=None, to_date=None):
    """Return {date: count} for one window of the contribution calendar.

    With no dates, GitHub serves its own default window — the trailing ~year that
    the profile page headlines.
    """
    url = f"https://github.com/users/{USER}/contributions"
    if from_date and to_date:
        url += f"?from={from_date}&to={to_date}"
    html = fetch(url)

    # The grid gives id -> date; the tool-tips give id -> count. Neither element
    # carries both, so they have to be joined on the cell id.
    by_id = {cell_id: day for day, cell_id in DAY_RE.findall(html)}
    out = {}
    for cell_id, text in TIP_RE.findall(html):
        day = by_id.get(cell_id)
        if not day:
            continue
        m = COUNT_RE.match(re.sub(r"<[^>]+>", "", text).strip())
        out[day] = int(m.group(1).replace(",", "")) if m else 0
    return out


def streaks(days, counts, today):
    """Current and longest run of consecutive days with at least one commit.

    A day with nothing on it only ends the current streak once it's in the past:
    at 9am you haven't necessarily pushed yet, so an empty *today* leaves
    yesterday's streak standing rather than zeroing it.
    """
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    current = 0
    for i in range(len(counts) - 1, -1, -1):
        if counts[i] > 0:
            current += 1
        elif days[i] == today and current == 0:
            continue        # today is still open for business
        else:
            break
    return current, longest


def build():
    today = date.today()
    merged = {}
    for year in range(today.year - YEARS_BACK, today.year + 1):
        merged.update(scrape(f"{year}-01-01", f"{year}-12-31"))
    if not merged:
        raise RuntimeError("no contribution days parsed — markup probably changed")

    # A calendar-year request returns the whole year, so the current year arrives
    # padded with empty days that haven't happened yet. Left in, they'd read as a
    # broken streak and a chart trailing off to nothing.
    d0, d1 = date.fromisoformat(min(merged)), today

    days, counts = [], []
    d = d0
    while d <= d1:
        iso = d.isoformat()
        days.append(iso)
        counts.append(merged.get(iso, 0))
        d += timedelta(days=1)

    # The headline "N contributions in the last year" comes from the unparameterised
    # window so the site's number is the same one the profile shows — GitHub anchors
    # that window to a Sunday, so summing the trailing 365 days lands slightly off.
    profile_year = scrape()
    best_i = max(range(len(counts)), key=lambda i: counts[i])
    today_iso = today.isoformat()
    current, longest = streaks(days, counts, today_iso)

    return {
        "user": USER,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start": days[0],
        "counts": counts,
        "total_window": sum(counts),
        "total_year": sum(profile_year.values()),
        "year_start": min(profile_year) if profile_year else days[0],
        "today": merged.get(today_iso, 0),
        "current_streak": current,
        "longest_streak": longest,
        "best_day": {"date": days[best_i], "count": counts[best_i]},
        "profile": f"https://github.com/{USER}",
    }


def guard(new):
    """Don't let a half-parsed scrape replace a good file.

    Contribution totals only ever grow, so a new total well below what we already
    published means the scrape broke, not that the commits vanished.
    """
    try:
        with open(OUT) as f:
            old = json.load(f)
    except (OSError, ValueError):
        return True
    if new["total_window"] < old.get("total_window", 0) * 0.9:
        print(f"REFUSING: total dropped {old.get('total_window')} -> "
              f"{new['total_window']}; keeping the old file", file=sys.stderr)
        return False
    return True


def main():
    try:
        data = build()
    except (urllib.error.URLError, RuntimeError, OSError) as e:
        print(f"fetch/parse failed: {e}", file=sys.stderr)
        return 1
    if not guard(data):
        return 1

    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    subprocess.run(["scp", "-q", OUT, DEST], check=True)
    subprocess.run(["ssh", "root@159.203.110.79",
                    "chown www-data:www-data /var/www/divinedavis/github.json"],
                   check=True)
    print(f"{data['updated']} ok — {data['total_year']} in the last year, "
          f"{data['today']} today, streak {data['current_streak']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
