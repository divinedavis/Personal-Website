#!/usr/bin/env python3
"""What Divine has actually shipped — iOS apps and live web apps.

Feeds the "Apps shipped" section on divinedavis.com. Same contract as the other
two generators: runs on the droplet, writes apps.json, scp's it to the web host,
and the page ships with the last-known numbers baked into the HTML.

NO APP STORE CONNECT KEY LIVES HERE, ON PURPOSE
-----------------------------------------------
The authoritative source for "is it on the App Store" would be ASC, but that
private key can create apps, upload builds and manage TestFlight — it does not
belong on a public-facing droplet to render a number. The public iTunes lookup
API answers the same question for free: query the developer id, and every app
that comes back is live.

BETA is therefore a declared list, and it is self-healing. Each entry is looked
up by bundle id on every run; the moment an app appears on the App Store it
moves itself from "TestFlight" to "App Store" and the two counts follow. Shipping
an app updates this page without anyone editing it. The only manual step is
adding a *new* app to BETA, which is one line.

WEB liveness is measured, not declared. Each site is fetched; a site has to fail
FAIL_STREAK runs in a row before it drops off the page, so one timeout on one
cron tick never blinks a project out of existence.

Deployed to /root/portfolio-stats/update_apps.py on 167.71.170.219, cron
*/15 * * * * -> /var/log/apps_stats.log.
"""

import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "apps-state.json"
OUT_PATH = HERE / "apps.json"
DEPLOY = "root@159.203.110.79:/var/www/divinedavis/apps.json"

# The App Store developer id. Everything published under it is discovered
# automatically — new releases need no change here.
ARTIST_ID = 980132489

# Built and in TestFlight, not yet on the App Store. Each is verified by bundle
# id every run: once Apple returns a result the app is counted as live instead,
# so this list only ever needs *adding* to.
#
# CanSub AI is deliberately absent — retired 2026-07-26, the ASC record outlives
# the product.
BETA = [
    ("Crease",             "com.divinedavis.crease"),
    ("Spendcap",           "com.divinedavis.spendcap"),
    ("Lovili",             "com.divinedavis.lovili"),
    ("Pulse",              "com.divinedavis.pulse"),
    ("Clock In",           "com.divinedavis.ClockIn"),
    ("ShypQuick",          "com.Dev.Shyp-Quick"),
    ("Less Spent",         "com.divinedavis.lessspent"),
    ("Find A Crib",        "com.divinedavis.findacrib"),
]

# Live web products. Counted only if they answer — see FAIL_STREAK.
WEB = [
    ("Find A Crib",                  "findacrib.com"),
    ("Collegiate Athletic Planning", "caprecruiting.com"),
    ("NEMO Seamless Gutter",         "nemoseamlessgutter.com"),
    ("Encounter",                    "encountersystem.com"),
    ("Jordan's Job Finder",          "jordansjobfinder.com"),
    ("Kinnkolk",                     "kinnkolk.com"),
    ("Trent's Fresh Spaces",         "trentsfreshspaces.com"),
    ("SlottingCal",                  "slottingcal.com"),
    ("WorkComp+ for Professionals",  "workcompapp.com"),
    ("Crease",                       "creasenyc.com"),
    ("Sputter Bets",                 "sputterbets.com"),
    ("Tech Job Recession Watch",     "divinedavis.com/tech-recession/"),
    ("Arina Tanacheva",              "arinatanacheva.com"),
    ("This site",                    "divinedavis.com"),
]

FAIL_STREAK = 3          # consecutive failures before a site drops off the page
TIMEOUT = 15
UA = "divinedavis.com-apps-check"


def log(msg):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def itunes(params):
    url = "https://itunes.apple.com/lookup?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        # Apple serves this as text/javascript; json.load does not care.
        return json.loads(r.read().decode("utf-8", "replace")).get("results", [])


def app_store_apps():
    """Everything live under the developer id, newest release first."""
    results = itunes({"id": ARTIST_ID, "entity": "software", "limit": 200})
    apps = []
    for r in results:
        if r.get("wrapperType") != "software":
            continue                       # the artist record itself
        apps.append({
            "name": r["trackName"],
            "status": "App Store",
            "version": r.get("version", ""),
            "genre": r.get("primaryGenreName", ""),
            "url": r.get("trackViewUrl", ""),
            "released": (r.get("releaseDate") or "")[:10],
        })
    apps.sort(key=lambda a: a["released"], reverse=True)
    return apps


def beta_apps(live_names):
    """BETA entries Apple does not yet know about. A hit means it shipped."""
    out = []
    for name, bundle in BETA:
        try:
            hit = itunes({"bundleId": bundle})
        except Exception as e:
            log(f"WARN itunes {bundle}: {e}")
            hit = []
        if hit:
            # It went live. app_store_apps() already counted it under Apple's
            # own name; nothing to add, and the list can be pruned at leisure.
            log(f"NOTE {name} ({bundle}) is on the App Store now — drop it from BETA")
            continue
        if name in live_names:
            continue
        out.append({"name": name, "status": "TestFlight", "version": "",
                    "genre": "", "url": "", "released": ""})
    return out


def check_web(domain):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(f"https://{domain}", method="GET",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            # A 2xx after redirects. urllib raises on 4xx/5xx, so getting here
            # with a sane status is the whole test.
            if 200 <= r.status < 300:
                return True, r.status
            return False, r.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception:
        return False, 0


def main():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    fails = state.get("fails", {})

    try:
        live = app_store_apps()
    except Exception as e:
        log(f"FATAL: App Store lookup failed: {e}")
        return 1
    if not live:
        log("REFUSING: App Store returned no apps; keeping the previous apps.json")
        return 1

    live_names = {a["name"] for a in live}
    ios = live + beta_apps(live_names)

    web, down = [], []
    for name, domain in WEB:
        ok, code = check_web(domain)
        if ok:
            fails[domain] = 0
            web.append({"name": name, "domain": domain})
        else:
            fails[domain] = fails.get(domain, 0) + 1
            down.append(f"{domain}({code}, {fails[domain]}x)")
            if fails[domain] < FAIL_STREAK:
                # Probably a blip: keep showing it, the page should not flicker.
                web.append({"name": name, "domain": domain})

    payload = {
        "ios_total": len(ios),
        "ios_live": len(live),
        "ios_beta": len(ios) - len(live),
        "web_live": len(web),
        "ios": ios,
        "web": web,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    STATE_PATH.write_text(json.dumps({"fails": fails}, indent=2) + "\n")

    log(f"{len(ios)} iOS ({len(live)} live, {payload['ios_beta']} beta), "
        f"{len(web)} web" + (f"; down: {', '.join(down)}" if down else ""))

    if "--no-deploy" not in sys.argv:
        p = subprocess.run(["scp", "-q", "-o", "BatchMode=yes",
                            str(OUT_PATH), DEPLOY], capture_output=True, text=True)
        if p.returncode != 0:
            log(f"WARN scp failed: {p.stderr.strip()[:200]}")
        else:
            subprocess.run(["ssh", "-o", "BatchMode=yes", "root@159.203.110.79",
                            "chown www-data:www-data /var/www/divinedavis/apps.json"],
                           capture_output=True, text=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
