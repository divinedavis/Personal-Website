#!/usr/bin/env python3
"""Total lines of code Divine has written across every GitHub repo.

Feeds the "Lines of code" section on divinedavis.com. Same shape as
update_github.py: this runs on the droplet, writes loc.json, and scp's it to the
web host; the page ships with the last-known numbers baked into the HTML so it
still reads correctly if the file is unreachable.

WHAT IT COUNTS, and why it is not GitHub's number
-------------------------------------------------
GitHub's /stats/contributors endpoint reports 806k additions. That number is
mostly not code: package-lock.json alone accounts for ~185k of it, and .pbxproj,
Unity .asset, notebook JSON and vendored trees make up most of the rest. This
counts additions on the default branch, authored by Divine, in files a person
actually typed — see EXCLUDE_* and COUNT_EXT below. Additions, not net: the
question is "how many lines have I written", and deleting your own code later
does not un-write it. Net is reported alongside as `net`.

Merge commits are skipped (--no-merges), matching how GitHub attributes work, so
a merge never double-counts the lines it brings in.

INCREMENTAL BY DESIGN
---------------------
One GraphQL call lists every repo with its default-branch head SHA. A repo whose
head has not moved since the last run is served from loc-state.json and never
touched over the network, so a normal run fetches nothing and finishes in about a
second. That is what makes a */5 cron reasonable against 66 repos.

The token is read from .env (GITHUB_TOKEN) and never written to disk: mirrors are
created with `git init --bare` and fetched by passing the authenticated URL on the
command line, so it never lands in .git/config.

Deployed to /root/portfolio-stats/update_loc.py on 167.71.170.219, cron
*/5 * * * * -> /var/log/loc_stats.log.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIRRORS = HERE / "loc-repos"
STATE_PATH = HERE / "loc-state.json"
OUT_PATH = HERE / "loc.json"
LOCK_PATH = HERE / ".loc.lock"
DEPLOY = "root@159.203.110.79:/var/www/divinedavis/loc.json"

# Commits with these author emails are Divine's. Everything else on the graph is
# a deploy bot, a growth engine, or a collaborator, and none of it is his typing.
EMAILS = {
    "divinejdavis@gmail.com",
    "divinedavis@users.noreply.github.com",
    "divine.davis@gmail.com",
    "divine@caprecruiting.com",
    "support@caprecruiting.com",
    "divin@example.com",
    "redacted@example.com",
}

# Some bots commit *as* Divine's email (the Juniper backup job does), so the
# email test alone is not enough — reject on author name too.
BOT_NAMES = {
    "juniper backup bot",
    "find a crib growth engine",
    "nemo growth engine",
    "nemo review agent",
    "claude",
    "nyc weather server",
    "symptomchecker deploy",
    "cap recruiting",
}

# Extension -> display language. An extension absent from this map is not code
# and is not counted: that is what keeps .json, .md, .ipynb, .xml, .plist and
# .storyboard out of the total. Add deliberately.
LANGS = {
    "py": "Python",
    "swift": "Swift",
    "ts": "TypeScript", "tsx": "TypeScript",
    "js": "JavaScript", "jsx": "JavaScript", "mjs": "JavaScript", "cjs": "JavaScript",
    "html": "HTML", "htm": "HTML",
    "css": "CSS", "scss": "CSS", "sass": "CSS", "less": "CSS",
    "sql": "SQL",
    "java": "Java",
    "kt": "Kotlin",
    "m": "Objective-C", "mm": "Objective-C", "h": "Objective-C",
    "c": "C/C++", "cc": "C/C++", "cpp": "C/C++", "hpp": "C/C++",
    "cs": "C#",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell",
    "go": "Go",
    "rb": "Ruby",
    "rs": "Rust",
    "php": "PHP",
    "dart": "Dart",
    "vue": "Vue", "svelte": "Svelte",
    "lua": "Lua",
    "r": "R",
    "scala": "Scala",
    "ex": "Elixir", "exs": "Elixir",
    "tf": "Terraform",
    "proto": "Protobuf",
    "graphql": "GraphQL",
    "yml": "Config", "yaml": "Config", "toml": "Config", "gradle": "Config",
}

# Directories nobody writes by hand.
EXCLUDE_SUBSTR = (
    "/node_modules/", "/pods/", "/vendor/", "/.venv/", "/venv/", "/site-packages/",
    "/carthage/", "/third_party/", "/dist/", "/build/", "/.next/", "/coverage/",
    "/deriveddata/", "/__pycache__/", "/xcuserdata/", "/xcshareddata/",
    "/.xcassets/", "/assets/vendor/", "/static/vendor/", "/migrations/versions/",
)
EXCLUDE_NAME = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "podfile.lock",
    "package.resolved", "poetry.lock", "gemfile.lock", "composer.lock",
    "cargo.lock", "uv.lock", "npm-shrinkwrap.json",
)
EXCLUDE_SUFFIX = (
    ".min.js", ".min.css", ".map", ".bundle.js", ".pbxproj", ".xcworkspacedata",
    ".lock", ".csv", ".tsv", ".geojson", ".ipynb", ".svg", ".xcscheme",
)

TOP_LANGS = 8
GRAPHQL = "https://api.github.com/graphql"

# Written code only ever grows. A total that drops by more than this means the
# filters or the auth broke, not that history changed — keep the good file.
DROP_GUARD = 0.90

# A rename shows up as "old/{a => b}/name.ext"; the post-rename path is what the
# extension test needs.
RENAME_RE = re.compile(r"\{[^{}]*=>\s*([^{}]*)\}")


def log(msg):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def load_env():
    """Read GITHUB_TOKEN from .env next to this script (chmod 600 on the box)."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def graphql(token, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        GRAPHQL, data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "divinedavis.com-loc-counter",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


REPO_QUERY = """
query($cursor: String) {
  viewer {
    repositories(first: 100, after: $cursor, isFork: false,
                 ownerAffiliations: [OWNER, COLLABORATOR],
                 affiliations: [OWNER, COLLABORATOR]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        isPrivate
        defaultBranchRef { name target { oid } }
      }
    }
  }
}
"""


def list_repos(token):
    repos, cursor = [], None
    while True:
        data = graphql(token, REPO_QUERY, {"cursor": cursor})["viewer"]["repositories"]
        for n in data["nodes"]:
            ref = n.get("defaultBranchRef")
            if not ref or not ref.get("target"):
                continue                      # empty repo, nothing to count
            repos.append({
                "name": n["nameWithOwner"],
                "private": n["isPrivate"],
                "branch": ref["name"],
                "head": ref["target"]["oid"],
            })
        if not data["pageInfo"]["hasNextPage"]:
            return repos
        cursor = data["pageInfo"]["endCursor"]


def git(args, cwd=None, check=True):
    p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}: {p.stderr.strip()[:300]}")
    return p.stdout


def language_of(path):
    """Display language for a path, or None if it is not hand-written code."""
    p = "/" + path.lower()
    if any(s in p for s in EXCLUDE_SUBSTR):
        return None
    base = p.rsplit("/", 1)[-1]
    if base in EXCLUDE_NAME or base.startswith("."):
        return None
    if any(base.endswith(s) for s in EXCLUDE_SUFFIX):
        return None
    if "." not in base:
        return None
    return LANGS.get(base.rsplit(".", 1)[-1])


def sync(repo, token):
    """Mirror the repo's default branch locally and return its counted totals."""
    owner, name = repo["name"].split("/")
    path = MIRRORS / f"{owner}_{name}.git"
    if not (path / "HEAD").exists():
        path.mkdir(parents=True, exist_ok=True)
        git(["init", "--bare", "-q", str(path)])

    # The token rides on the command line only, so it never reaches .git/config.
    url = f"https://x-access-token:{token}@github.com/{repo['name']}.git"
    branch = repo["branch"]
    git(["-C", str(path), "fetch", "--quiet", "--prune", url,
         f"+refs/heads/{branch}:refs/heads/{branch}"])

    out = git(["-C", str(path), "log", branch, "--no-merges", "--numstat",
               "--format=@@%ae|%an"])

    add = dele = commits = 0
    langs = Counter()
    mine = False
    for line in out.splitlines():
        if line.startswith("@@"):
            email, _, author = line[2:].partition("|")
            mine = email.lower() in EMAILS and author.lower() not in BOT_NAMES
            if mine:
                commits += 1
            continue
        if not mine or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":      # "-" is a binary file
            continue
        a, d, path_str = parts
        path_str = RENAME_RE.sub(r"\1", path_str).replace("//", "/")
        lang = language_of(path_str)
        if not lang:
            continue
        add += int(a)
        dele += int(d)
        langs[lang] += int(a)

    return {"head": repo["head"], "added": add, "deleted": dele,
            "commits": commits, "langs": dict(langs), "private": repo["private"]}


def main():
    # A steady-state run fetches nothing and takes about a second, so */5 never
    # overlaps — but the FIRST run has to mirror every repo, which is minutes and
    # hundreds of megabytes. Without this, cron stacks concurrent clones into the
    # same loc-repos/ paths and they race each other writing loc-state.json. The
    # same applies after any long outage, when every mirror is stale at once.
    # Skip quietly rather than logging: a skipped tick is the lock working, and
    # */5 makes noise fast.
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0

    token = load_env()
    if not token:
        log("FATAL: no GITHUB_TOKEN in environment or .env")
        return 1

    MIRRORS.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}

    try:
        repos = list_repos(token)
    except (urllib.error.URLError, RuntimeError) as e:
        log(f"FATAL: repo list failed: {e}")
        return 1

    fresh, changed, failed = {}, [], []
    for repo in repos:
        cached = state.get(repo["name"])
        if cached and cached.get("head") == repo["head"]:
            fresh[repo["name"]] = cached
            continue
        try:
            fresh[repo["name"]] = sync(repo, token)
            changed.append(repo["name"])
        except Exception as e:                       # one bad repo must not
            log(f"WARN {repo['name']}: {e}")         # zero out the whole total
            failed.append(repo["name"])
            if cached:
                fresh[repo["name"]] = cached

    total_add = sum(r["added"] for r in fresh.values())
    total_del = sum(r["deleted"] for r in fresh.values())
    commits = sum(r["commits"] for r in fresh.values())

    langs = Counter()
    for r in fresh.values():
        langs.update(r["langs"])
    ranked = langs.most_common()
    top = [{"name": n, "lines": v} for n, v in ranked[:TOP_LANGS]]
    tail = sum(v for _, v in ranked[TOP_LANGS:])
    if tail:
        top.append({"name": "Other", "lines": tail})

    # Only the count ships. loc.json is served publicly, and a per-repo
    # breakdown would put private repo names on a public URL.
    repos_with_code = sum(1 for r in fresh.values() if r["added"] > 0)

    prev = json.loads(OUT_PATH.read_text()) if OUT_PATH.exists() else None
    if prev and prev.get("added") and total_add < prev["added"] * DROP_GUARD:
        log(f"REFUSING: total fell {prev['added']:,} -> {total_add:,} "
            f"({len(failed)} repos failed); keeping the previous loc.json")
        return 1

    payload = {
        "added": total_add,
        "deleted": total_del,
        "net": total_add - total_del,
        "commits": commits,
        "repos": repos_with_code,
        "languages": top,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    STATE_PATH.write_text(json.dumps(fresh, indent=2) + "\n")

    log(f"{total_add:,} lines across {payload['repos']} repos "
        f"({commits:,} commits); {len(changed)} repo(s) re-counted"
        + (f", {len(failed)} failed" if failed else ""))

    if "--no-deploy" not in sys.argv:
        p = subprocess.run(["scp", "-q", "-o", "BatchMode=yes",
                            str(OUT_PATH), DEPLOY], capture_output=True, text=True)
        if p.returncode != 0:
            log(f"WARN scp failed: {p.stderr.strip()[:200]}")
        else:
            subprocess.run(["ssh", "-o", "BatchMode=yes", "root@159.203.110.79",
                            "chown www-data:www-data /var/www/divinedavis/loc.json"],
                           capture_output=True, text=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
