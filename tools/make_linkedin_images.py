#!/usr/bin/env python3
"""Renders the LinkedIn profile art for divinedavis.com — banner and thumbnail.

LinkedIn takes both as uploads and scrapes neither, so they go stale the moment
the numbers on the page move. This makes regenerating them a one-liner instead
of a design session:

    python3 tools/make_linkedin_images.py

It reads the same JSON the live page reads, fills the {{TOKENS}} in each
template, and screenshots them with headless Chrome into marketing/:

    linkedin-banner.png     1584x396  the profile header
    linkedin-thumbnail.png  1200x627  the Featured link card

Both carry the same three numbers so the profile does not contradict itself.

WHY IT READS THE LIVE SITE AND NOT THE DROPLET
----------------------------------------------
Unlike update_apps.py / update_github.py / update_loc.py, this runs on a laptop,
not on the droplet, and it needs no credentials at all. divinedavis.com already
publishes every number it needs. That also means these images can only ever
claim what the page itself is claiming, which is the point — they should never
disagree.

Any endpoint that 404s or times out falls back to the last-known value baked
into index.html, exactly the way the page degrades with JS off. loc.json is
currently in that state: the lines-of-code generator on the droplet has no
GITHUB_TOKEN in its .env, so the site and these images both show the baked-in
figure. Fix that and rerun this to pick up the real one.

OUTPUT SIZE
-----------
Each template declares its own pixel size and is screenshotted at exactly that
size, rendered at 2x so the numbers stay crisp after LinkedIn re-encodes them.
The crop each one has to survive is documented in the template itself, not here
— that geometry belongs next to the CSS that answers it.
"""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
INDEX = REPO / "index.html"
OUT_DIR = REPO / "marketing"

SITE = "https://divinedavis.com"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SCALE = 2
TIMEOUT = 10

# (template, output name, css pixel width, css pixel height)
TARGETS = [
    ("banner.html", "linkedin-banner.png", 1584, 396),
    ("thumbnail.html", "linkedin-thumbnail.png", 1200, 627),
]


def fetch_json(name):
    """The live copy of one stats file, or None if it is not being served."""
    url = "%s/%s?t=art" % (SITE, name)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as err:
        print("  %s unavailable (%s), using the baked-in value" % (name, err))
        return None


def baked_in(attr, key):
    """The last-known value for a stat, read out of index.html.

    index.html carries every number twice over: once as a data attribute the
    scripts overwrite, and once as the text a no-JS visitor sees. That text is
    the fallback here, so there is still exactly one place a stale number can
    live.
    """
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r'%s="%s"[^>]*>([^<]+)<' % (attr, key), html)
    if not match:
        sys.exit("index.html has no %s=\"%s\" — the markup moved" % (attr, key))
    return match.group(1).strip()


def comma(n):
    return "{:,}".format(int(n))


def read_stats():
    """The three numbers both images share, live where possible."""
    github = fetch_json("github.json")
    contributions = comma(github["total_year"]) if github \
        else baked_in("data-gh-stat", "total_year")

    loc = fetch_json("loc.json")
    lines = comma(loc["added"]) if loc \
        else baked_in("data-loc-stat", "added")

    apps = fetch_json("apps.json")
    if apps:
        shipped = comma(apps["ios_total"] + apps["web_live"])
    else:
        shipped = comma(int(baked_in("data-apps-stat", "ios_total"))
                        + int(baked_in("data-apps-stat", "web_live")))

    return {
        "{{CONTRIBUTIONS}}": contributions,
        "{{LOC}}": lines,
        "{{APPS}}": shipped,
    }


def render(template, out_name, width, height, stats):
    html = (HERE / template).read_text(encoding="utf-8")
    for token, value in stats.items():
        if token not in html:
            sys.exit("%s no longer contains %s" % (template, token))
        html = html.replace(token, value)

    # Chrome screenshots a file:// URL, so the filled-in copy has to exist on
    # disk. It is written next to the template and removed afterwards rather
    # than committed — the PNG is the artifact worth keeping.
    filled = HERE / (template + ".filled.html")
    filled.write_text(html, encoding="utf-8")

    out = OUT_DIR / out_name
    try:
        subprocess.run([
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=%d" % SCALE,
            "--window-size=%d,%d" % (width, height),
            "--screenshot=%s" % out,
            filled.as_uri(),
        ], check=True, capture_output=True)
    finally:
        filled.unlink(missing_ok=True)

    print("  %s (%dx%d)" % (out_name, width * SCALE, height * SCALE))


def main():
    if not Path(CHROME).exists():
        sys.exit("Google Chrome is not installed at %s" % CHROME)

    print("Reading stats from %s" % SITE)
    stats = read_stats()
    print("  %s commits/yr, %s lines, %s apps"
          % (stats["{{CONTRIBUTIONS}}"], stats["{{LOC}}"], stats["{{APPS}}"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Rendering into %s/" % OUT_DIR.name)
    for template, out_name, width, height in TARGETS:
        render(template, out_name, width, height, stats)


if __name__ == "__main__":
    main()
