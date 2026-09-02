#!/usr/bin/env python3
"""Who in the NYC panel is actually ahead of divinedavis on public commits.

The site's "New Yorkers ahead" tile is an *estimate* — population times one
minus the percentile — not a headcount. This answers the literal question
behind it by reusing update_nycrank.py's own frozen frame and GraphQL pass, so
the numbers match the site exactly, and then naming the panel members above us
instead of weighting them away.

Run it on the droplet (167.71.170.219), never here: the panel logins are real
New Yorkers who did not opt into being ranked, nyc-cohort.json is gitignored,
and this repo is public. The script prints to stdout and writes nothing, so
nothing it learns can end up in a published file by accident.

    ssh root@167.71.170.219 'cd /root/portfolio-stats && python3 nycrank_who_ahead.py'
"""
import json, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "/root/portfolio-stats")
import update_nycrank as N

tok = N.token()
until = datetime.now(timezone.utc).replace(microsecond=0)
since = until - timedelta(days=N.WINDOW_DAYS)
siso, uiso = since.strftime("%Y-%m-%dT%H:%M:%SZ"), until.strftime("%Y-%m-%dT%H:%M:%SZ")

frame = json.load(open(N.COHORT))
pop, members = frame["population"], frame["members"]
mine = N.contributions(tok, [N.USER], siso, uiso)[N.USER.lower()]
got = N.contributions(tok, [m["login"] for m in members], siso, uiso)

resolved = [m for m in members if m["login"].lower() in got]
drawn = {}
for m in resolved:
    drawn[m["stratum"]] = drawn.get(m["stratum"], 0) + 1

ahead = []
for m in resolved:
    g = got[m["login"].lower()]
    if g["commits"] > mine["commits"]:
        ahead.append({"login": m["login"], "stratum": m["stratum"],
                      "commits": g["commits"], "total": g["total"],
                      "active_days": g["active_days"],
                      "weight": pop.get(m["stratum"], 0) / drawn[m["stratum"]]})
ahead.sort(key=lambda r: -r["commits"])

print(json.dumps({
    "mine": mine["commits"], "sample_n": len(resolved),
    "ahead_in_panel": len(ahead),
    "estimated_ahead_citywide": round(sum(a["weight"] for a in ahead)),
    "accounts": ahead,
}, indent=1))
