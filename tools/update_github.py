#!/usr/bin/env python3
"""Publish divinedavis.com's GitHub contribution numbers as github.json.

Numbers come from the GraphQL `contributionsCollection`, which needs a token.
This script originally scraped the public profile fragment instead, precisely so
that no secret had to live on the droplet — but that fragment is only eventually
consistent for the *current* day. Measured 2026-08-08: GraphQL reported 14
contributions and the public API showed 19 push events, while the scrape still
said "No contributions on August 8th" at 7pm UTC. Every day looked like that —
today's number surfaced hours late and low, then backfilled overnight — so the
site's TODAY tile and current streak were wrong for most of each day.

GraphQL is authoritative in real time. The scrape survives as `scrape()` and is
used as a fallback when the token is missing or rejected, so an expired token
degrades to late-but-correct history instead of freezing the file.

Layout of the output is a dense array, not a list of {date, count} objects:
`counts[i]` is the day `start + i`, so a three-year window is ~4KB of JSON
instead of ~60KB.

Runs from cron on 167.71.170.219 and scp's the result to the web host (159).
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

USER = "divinedavis"
YEARS_BACK = 2          # this calendar year plus the two before it
OUT = "/root/portfolio-stats/github.json"
DEST = "root@159.203.110.79:/var/www/divinedavis/github.json"

# A classic PAT with NO scopes is enough — contributionsCollection on a public
# profile needs no permission beyond being authenticated. Kept out of the repo;
# the droplet reads it from ENV_FILE (mode 0600).
ENV_FILE = "/root/portfolio-stats/.env"
GRAPHQL_URL = "https://api.github.com/graphql"

# GitHub 403s the default urllib agent.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# The droplet runs UTC, but GitHub buckets contributions in the profile's own
# timezone. Using the box's date rolls "today" over at 8pm ET and reports a zero
# for a day that's still being worked on.
LOCAL_TZ = ZoneInfo("America/New_York")

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


def token():
    """The PAT, from the environment or ENV_FILE. None if there isn't one."""
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok.strip()
    try:
        with open(ENV_FILE) as f:
            for line in f:
                key, _, value = line.partition("=")
                if key.strip() == "GITHUB_TOKEN":
                    return value.strip().strip("'\"")
    except OSError:
        pass
    return None


QUERY = """
query($login:String!, $from:DateTime, $to:DateTime) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def graphql(tok, from_date=None, to_date=None):
    """Return {date: count} for one window, straight from the API.

    from/to are plain dates here; GraphQL wants DateTimes, and it clamps any
    span longer than a year, which is why build() still walks year by year.
    Omitting both gives GitHub's own trailing-year window — the one the profile
    headline counts, anchored to a Sunday rather than to today minus 365.
    """
    variables = {"login": USER}
    if from_date and to_date:
        variables["from"] = f"{from_date}T00:00:00Z"
        variables["to"] = f"{to_date}T23:59:59Z"

    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {tok}",
                 "Content-Type": "application/json",
                 "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)

    # GraphQL reports its own failures inside a 200, so this has to be checked
    # explicitly or a bad token reads as an empty calendar.
    if body.get("errors"):
        raise RuntimeError(body["errors"][0].get("message", "graphql error"))

    weeks = (body["data"]["user"]["contributionsCollection"]
             ["contributionCalendar"]["weeks"])
    return {d["date"]: d["contributionCount"]
            for w in weeks for d in w["contributionDays"]}


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


def source():
    """Pick the calendar fetcher: GraphQL when we have a working token.

    The probe is a real query, not just "is the token non-empty" — an expired or
    revoked PAT answers 200 with an errors array, and falling back on that is the
    whole point of keeping the scraper around.
    """
    tok = token()
    if not tok:
        print("WARN: no GITHUB_TOKEN — falling back to the scrape, which lags "
              "for the current day", file=sys.stderr)
        return scrape
    try:
        graphql(tok, "2026-01-01", "2026-01-07")
    except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as e:
        print(f"WARN: GITHUB_TOKEN rejected ({e}) — falling back to the scrape",
              file=sys.stderr)
        return scrape
    return lambda f=None, t=None: graphql(tok, f, t)


def published():
    """The last file this script wrote, or None on the first run."""
    try:
        with open(OUT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def build():
    today = datetime.now(LOCAL_TZ).date()
    today_iso = today.isoformat()
    calendar = source()
    merged = {}
    for year in range(today.year - YEARS_BACK, today.year + 1):
        merged.update(calendar(f"{year}-01-01", f"{year}-12-31"))
    if not merged:
        raise RuntimeError("no contribution days parsed — markup probably changed")

    # GraphQL isn't immune to the current-day lag either: its replicas disagree
    # about today. Measured 2026-08-10, alternating runs returned today as 13
    # and 0 while the trailing-year total kept growing, so TODAY and the streak
    # flapped all afternoon. A day's count never shrinks while the day is in
    # progress, so the number already published is a floor for the fresh one.
    old = published()
    if old and "start" in old:
        i = (today - date.fromisoformat(old["start"])).days
        if 0 <= i < len(old.get("counts", [])):
            merged[today_iso] = max(merged.get(today_iso, 0), old["counts"][i])

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
    profile_year = calendar()
    best_i = max(range(len(counts)), key=lambda i: counts[i])
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
    dry_run = "--dry-run" in sys.argv     # for checking a change off the droplet
    try:
        data = build()
    except (urllib.error.URLError, RuntimeError, OSError) as e:
        print(f"fetch/parse failed: {e}", file=sys.stderr)
        return 1
    if dry_run:
        print(json.dumps({k: v for k, v in data.items() if k != "counts"},
                         indent=2))
        return 0
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
