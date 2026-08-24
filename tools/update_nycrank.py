#!/usr/bin/env python3
"""Publish divinedavis.com's NYC commit ranking as nycrank.json.

The claim on the site is "top N% of New York developers on GitHub", so the
number behind it has to be measured, not asserted. It is:

  1. A *frame* of GitHub accounts whose profile location says New York, built
     from the user-search API and stratified by follower count. Followers are
     the dominant confounder in search ranking — search sorts by best-match,
     which is roughly popularity, so an unstratified sample is all famous
     accounts and puts everyone in the 99th percentile. Sampling a fixed number
     from each follower bucket and then weighting each bucket back to its true
     population size fixes that. Rebuilt monthly; the panel is otherwise frozen
     so day-over-day movement is real movement, not resampling noise.

  2. A daily pass over that frozen panel pulling each member's public commit
     count in the same trailing window as ours, via GraphQL
     contributionsCollection. ~41 requests a day — deliberately cheap; the
     expensive part (the ~126 search calls that build the frame) runs monthly.

Everyone is compared on PUBLIC commits only. contributionsCollection on someone
else's account can't see their private work, so counting our own private
commits here would be scoring ourselves on a scale nobody else is measured on.
That drops the headline number, and it is the only honest version of it.

The panel members' logins never leave the droplet. nyc-cohort.json is
gitignored and nycrank.json carries aggregates only — publishing a list of
named New Yorkers ranked by how much they commit is not the point of the
section, and they did not opt into it.

Runs from cron on 167.71.170.219 and scp's the result to the web host (159).
"""

import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

USER = "divinedavis"
WINDOW_DAYS = 183                      # the trailing six months
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "nycrank.json")
COHORT = os.path.join(BASE, "nyc-cohort.json")
DEST = "root@159.203.110.79:/var/www/divinedavis/nycrank.json"
ENV_FILE = os.path.join(BASE, ".env")

GRAPHQL_URL = "https://api.github.com/graphql"
SEARCH_URL = "https://api.github.com/search/users"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Locations people in the five boroughs actually type. "New York" alone also
# catches upstate, which is why the label on the site says New York and not NYC.
LOCATIONS = ["New York", "NYC", "Brooklyn", "Manhattan", "Queens, NY"]
# Follower buckets, disjoint and exhaustive, used both to stratify the draw and
# to weight it back to the population.
STRATA = ["0..0", "1..2", "3..5", "6..10", "11..25",
          "26..50", "51..100", "101..500", "501..*"]
SAMPLE_YEARS = list(range(2011, 2026))
PER_STRATUM = 110                      # ~990 accounts, ~41 GraphQL calls a day
FRAME_MAX_AGE_DAYS = 30
SEARCH_SLEEP = 2.2                     # search API allows 30/min authenticated

# Cohorts the site reports, as a floor on public commits in the window. The
# unfiltered population is 46% accounts that have never pushed anything, so a
# percentile against it flatters and means nothing; the ladder exists so the
# comparison gets progressively harder and the reader can pick their own bar.
COHORTS = [
    ("any", 1, "Everyone with a New York profile who committed at all"),
    ("active", 50, "Accounts past 50 commits \u2014 real, in-use accounts"),
    ("working", 250, "Accounts committing at a full-time pace"),
    ("heavy", 1000, "Accounts past 1,000 commits in six months"),
]


def token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in ("GITHUB_TOKEN", "GH_TOKEN"):
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    raise RuntimeError("no GitHub token in env or " + ENV_FILE)


def api(url, tok, data=None, retries=4):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"User-Agent": UA, "Authorization": "bearer " + tok,
               "Accept": "application/vnd.github+json"}
    if body:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            # 403/429 is secondary rate limiting; 5xx is GitHub having a
            # moment. Both are worth waiting out — a dropped batch is 25
            # accounts silently missing from the panel.
            if e.code in (403, 429) or e.code >= 500:
                if attempt < retries - 1:
                    time.sleep(min(60, 5 * 2 ** attempt))
                    continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def search_users(tok, query, per_page=100):
    q = urllib.parse.urlencode({"q": query, "per_page": per_page})
    try:
        data = api(SEARCH_URL + "?" + q, tok)
    except urllib.error.HTTPError:
        return 0, []
    return data.get("total_count", 0), [i["login"] for i in data.get("items", [])]


def build_frame(tok):
    """Draw a fresh stratified panel and record each stratum's true size."""
    print("building frame...", flush=True)
    pop, pool = {}, {s: set() for s in STRATA}
    for s in STRATA:
        total, _ = search_users(tok, f'location:"New York" followers:{s} type:user', 1)
        pop[s] = total
        time.sleep(SEARCH_SLEEP)
        # Search caps any one query at 1000 results, so the pool is assembled
        # from per-year slices rather than paging one giant query.
        for y in SAMPLE_YEARS:
            _, logins = search_users(
                tok, f'location:"New York" followers:{s} type:user '
                     f'created:{y}-01-01..{y}-12-31')
            pool[s].update(logins)
            time.sleep(SEARCH_SLEEP)
        print(f"  {s}: population {pop[s]}, pool {len(pool[s])}", flush=True)

    # Seeded so a rebuild that happens to hit the same pool redraws the same
    # panel, and the series doesn't jump for no reason.
    rng = random.Random(1729)
    members = []
    for s in STRATA:
        us = sorted(pool[s])
        rng.shuffle(us)
        for u in us[:PER_STRATUM]:
            members.append({"stratum": s, "login": u})
    if len(members) < PER_STRATUM * len(STRATA) * 0.5:
        raise RuntimeError(f"frame too thin: {len(members)} accounts")

    frame = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "population": pop, "members": members}
    with open(COHORT, "w") as f:
        json.dump(frame, f, separators=(",", ":"))
    print(f"frame built: {len(members)} accounts, "
          f"population {sum(pop.values()):,}", flush=True)
    return frame


def load_frame(tok, rebuild=False):
    if not rebuild:
        try:
            with open(COHORT) as f:
                frame = json.load(f)
            age = datetime.now(timezone.utc) - datetime.strptime(
                frame["built"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if age.days < FRAME_MAX_AGE_DAYS and frame.get("members"):
                return frame
            print(f"frame is {age.days}d old, rebuilding", flush=True)
        except (OSError, ValueError, KeyError):
            pass
    return build_frame(tok)


def contributions(tok, logins, since, until):
    """Public commits + calendar totals for a list of logins, 25 at a time."""
    out, batch = {}, 25
    frag = ('contributionsCollection(from: "%s", to: "%s") '
            '{ totalCommitContributions '
            '  contributionCalendar { totalContributions '
            '    weeks { contributionDays { contributionCount } } } }'
            % (since, until))
    for i in range(0, len(logins), batch):
        chunk = logins[i:i + batch]
        parts = ['u%d: user(login: "%s") { login %s }' % (j, u, frag)
                 for j, u in enumerate(chunk)]
        try:
            res = api(GRAPHQL_URL, tok, {"query": "{ " + " ".join(parts) + " }"})
        except urllib.error.HTTPError as e:
            print(f"  batch {i} failed: {e}", file=sys.stderr)
            continue
        data = res.get("data") or {}
        for j, u in enumerate(chunk):
            node = data.get("u%d" % j)
            if not node:
                continue          # renamed, deleted, or suspended since the draw
            cc = node["contributionsCollection"]
            days = [d["contributionCount"]
                    for w in cc["contributionCalendar"]["weeks"]
                    for d in w["contributionDays"]]
            out[node["login"].lower()] = {
                "commits": cc["totalCommitContributions"],
                "total": cc["contributionCalendar"]["totalContributions"],
                "active_days": sum(1 for d in days if d > 0),
                "days": len(days),
                "best_day": max(days) if days else 0,
            }
        time.sleep(0.3)
    return out


def weighted(rows, floor):
    """(population, count above us, median) for everyone at or past `floor`."""
    d = sorted((r["commits"], r["weight"]) for r in rows if r["commits"] >= floor)
    total = sum(w for _, w in d)
    return d, total


def percentile_of(d, total, value):
    below = sum(w for v, w in d if v < value)
    return (below / total * 100.0) if total else 0.0


def quantile(d, total, q):
    acc = 0.0
    for v, w in d:
        acc += w
        if acc >= q * total:
            return v
    return d[-1][0] if d else 0


def build():
    tok = token()
    until = datetime.now(timezone.utc).replace(microsecond=0)
    since = until - timedelta(days=WINDOW_DAYS)
    siso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    uiso = until.strftime("%Y-%m-%dT%H:%M:%SZ")

    frame = load_frame(tok, rebuild="--rebuild-frame" in sys.argv)
    pop = frame["population"]
    members = frame["members"]

    # Queried as a plain user node exactly like everyone else, so the number is
    # public-only on both sides of the comparison.
    mine = contributions(tok, [USER], siso, uiso).get(USER.lower())
    if not mine:
        raise RuntimeError("could not read own contributions")

    got = contributions(tok, [m["login"] for m in members], siso, uiso)
    resolved = [m for m in members if m["login"].lower() in got]
    if len(resolved) < len(members) * 0.7:
        raise RuntimeError(f"only {len(resolved)}/{len(members)} accounts "
                           f"resolved; refusing to score against a partial panel")

    # Each surviving account stands in for population/sampled others in its
    # bucket. Recomputing the denominator from what actually resolved (not from
    # PER_STRATUM) keeps the weights right as accounts disappear.
    drawn = {}
    for m in resolved:
        drawn[m["stratum"]] = drawn.get(m["stratum"], 0) + 1
    rows = []
    for m in resolved:
        s = m["stratum"]
        rows.append({"commits": got[m["login"].lower()]["commits"],
                     "weight": pop.get(s, 0) / drawn[s]})

    cohorts = []
    for key, floor, label in COHORTS:
        d, total = weighted(rows, floor)
        if total <= 0:
            continue
        pct = percentile_of(d, total, mine["commits"])
        cohorts.append({
            "key": key, "label": label, "floor": floor,
            "population": round(total),
            "percentile": round(pct, 1),
            "above": round(total * (1 - pct / 100.0)),
            "median": quantile(d, total, 0.5),
            "p90": quantile(d, total, 0.9),
        })

    head = cohorts[0]
    return {
        "user": USER,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": WINDOW_DAYS,
        "window_start": since.date().isoformat(),
        "window_end": until.date().isoformat(),
        "commits": mine["commits"],
        "contributions": mine["total"],
        "active_days": mine["active_days"],
        "window_span": mine["days"],
        "best_day": mine["best_day"],
        "percentile": head["percentile"],
        "above": head["above"],
        "population": head["population"],
        "frame_population": sum(pop.values()),
        "frame_built": frame["built"],
        "sample_n": len(resolved),
        "cohorts": cohorts,
    }


def guard(new):
    """A panel that half-resolves would read as a promotion, not a failure."""
    try:
        with open(OUT) as f:
            old = json.load(f)
    except (OSError, ValueError):
        return True
    if new["sample_n"] < old.get("sample_n", 0) * 0.8:
        print(f"REFUSING: panel shrank {old.get('sample_n')} -> "
              f"{new['sample_n']}; keeping the old file", file=sys.stderr)
        return False
    if new["commits"] <= 0:
        print("REFUSING: own commit count came back zero", file=sys.stderr)
        return False
    return True


def main():
    try:
        data = build()
    except (urllib.error.URLError, urllib.error.HTTPError,
            RuntimeError, OSError, ValueError) as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1

    if "--dry-run" in sys.argv:
        print(json.dumps(data, indent=2))
        return 0
    if not guard(data):
        return 1

    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    subprocess.run(["scp", "-q", OUT, DEST], check=True)
    subprocess.run(["ssh", "root@159.203.110.79",
                    "chown www-data:www-data /var/www/divinedavis/nycrank.json"],
                   check=True)
    print(f"{data['updated']} ok — {data['commits']} commits, "
          f"{data['percentile']}th pct of {data['population']:,} NYC accounts "
          f"({data['sample_n']} sampled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
