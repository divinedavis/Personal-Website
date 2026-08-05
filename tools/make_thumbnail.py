#!/usr/bin/env python3
"""Renders the LinkedIn Featured thumbnail for divinedavis.com.

The Featured section on a LinkedIn profile shows a link as a card with a
thumbnail image. LinkedIn will not scrape one from the site, so it has to be
uploaded by hand — and a hand-uploaded image goes stale the moment the numbers
on the page move. This script makes regenerating it a one-liner instead of a
design session:

    python3 tools/make_thumbnail.py

It reads the same JSON the live page reads, drops the numbers into
thumbnail.html, and screenshots that file with headless Chrome to
marketing/linkedin-thumbnail.png.

WHY IT READS THE LIVE SITE AND NOT THE DROPLET
----------------------------------------------
Unlike update_apps.py / update_github.py / update_loc.py, this runs on a laptop,
not on the droplet, and it needs no credentials at all. divinedavis.com already
publishes every number it needs. That also means the thumbnail can only ever
claim what the page itself is claiming, which is the point — the two should
never disagree.

Any endpoint that 404s or times out falls back to the last-known value baked
into index.html, exactly the way the page degrades with JS off. loc.json is
currently in that state: the lines-of-code generator needs a read-only PAT that
is not yet on the droplet, so the site and this thumbnail both show the baked-in
figure.

OUTPUT SIZE
-----------
1200x627 is LinkedIn's link-preview ratio (1.91:1), rendered at 2x for a
2400x1254 file so the numbers stay crisp after LinkedIn re-encodes it. The
ratio, not the pixel count, is what the layout depends on.
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
TEMPLATE = HERE / "thumbnail.html"
INDEX = REPO / "index.html"
OUT = REPO / "marketing" / "linkedin-thumbnail.png"

SITE = "https://divinedavis.com"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

WIDTH, HEIGHT, SCALE = 1200, 627, 2
TIMEOUT = 10


def fetch_json(name):
    """The live copy of one stats file, or None if it is not being served."""
    url = "%s/%s?t=thumb" % (SITE, name)
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


def main():
    print("Reading stats from %s" % SITE)

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

    print("  %s commits/yr, %s lines, %s apps" % (contributions, lines, shipped))

    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("{{CONTRIBUTIONS}}", contributions),
                         ("{{LOC}}", lines),
                         ("{{APPS}}", shipped)):
        if token not in html:
            sys.exit("thumbnail.html no longer contains %s" % token)
        html = html.replace(token, value)

    # Chrome screenshots a file:// URL, so the filled-in copy has to exist on
    # disk. It is written next to the template and removed afterwards rather
    # than committed — the PNG is the artifact worth keeping.
    filled = HERE / "thumbnail.filled.html"
    filled.write_text(html, encoding="utf-8")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not Path(CHROME).exists():
        sys.exit("Google Chrome is not installed at %s" % CHROME)

    try:
        subprocess.run([
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=%d" % SCALE,
            "--window-size=%d,%d" % (WIDTH, HEIGHT),
            "--screenshot=%s" % OUT,
            filled.as_uri(),
        ], check=True, capture_output=True)
    finally:
        filled.unlink(missing_ok=True)

    print("Wrote %s (%dx%d)" % (OUT, WIDTH * SCALE, HEIGHT * SCALE))


if __name__ == "__main__":
    main()
