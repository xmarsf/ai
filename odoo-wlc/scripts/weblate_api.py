#!/usr/bin/env python3
"""Weblate REST helpers for odoo-wlc. Stdlib only; auth from ~/.weblate."""
import configparser
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# translate.vdx.vn rejects the default Python-urllib agent with HTTP 403.
USER_AGENT = "odoo-wlc/1.0"


def load_config(path="~/.weblate"):
    url, key = os.environ.get("WLC_URL"), os.environ.get("WLC_KEY")
    if url and key:
        return {"url": url, "key": key}
    # delimiters=('=',) — option names are URLs; the default ':' delimiter
    # would split "https://host/api/" at "https".
    cp = configparser.ConfigParser(delimiters=('=',))
    if not cp.read(os.path.expanduser(path)):
        raise SystemExit("error: no ~/.weblate and no WLC_URL/WLC_KEY — run wlc setup first")
    url = cp.get("weblate", "url").strip().rstrip("/") + "/"
    keys = {opt.strip().rstrip("/") + "/": val.strip() for opt, val in cp.items("keys")}
    key = keys.get(url) or next((v for v in keys.values() if v), None)
    if not key:
        raise SystemExit("error: no API key for %s in %s" % (url, path))
    return {"url": url, "key": key}


def api_get(cfg, path):
    full = cfg["url"] + path.lstrip("/")
    req = urllib.request.Request(full, headers={"Authorization": "Token " + cfg["key"],
                                                "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("error: Weblate API %s returned %s" % (full, e.code))
    except urllib.error.URLError as e:
        raise SystemExit("error: Weblate API %s unreachable: %s" % (full, e.reason))


def api_get_paged(cfg, path):
    """Follow DRF pagination, returning the concatenated `results`."""
    out, page = [], api_get(cfg, path)
    while True:
        out.extend(page["results"])
        nxt = page.get("next")
        if not nxt:
            return out
        page = api_get(cfg, nxt[len(cfg["url"]):] if nxt.startswith(cfg["url"]) else nxt)


def construct_mr_url(repo, source_branch, target_branch):
    clean = repo.split("://", 1)[-1].split("@", 1)[-1]        # drop scheme + userinfo
    if clean.endswith(".git"):
        clean = clean[:-len(".git")]
    host, _, proj = clean.partition("/")
    q = urllib.parse.urlencode({
        "merge_request[source_branch]": source_branch,
        "merge_request[target_branch]": target_branch})
    return "https://%s/%s/-/merge_requests/new?%s" % (host, proj, q)


def cmd_components(cfg, project):
    return [{"slug": c["slug"], "name": c["name"]}
            for c in api_get_paged(cfg, "projects/%s/components/" % project)]


def component_stats(cfg, project, slug, lang):
    """Weblate statistics carry no `untranslated` field — derive it."""
    try:
        s = api_get(cfg, "translations/%s/%s/%s/statistics/" % (project, slug, lang))
    except SystemExit:                      # 404 = language not present on component
        return {"slug": slug, "untranslated": None, "fuzzy": None, "total": None}
    return {"slug": slug,
            "untranslated": s["total"] - s["translated"] - s["fuzzy"],
            "fuzzy": s["fuzzy"],
            "total": s["total"]}


def cmd_stats(cfg, project, lang):
    slugs = [c["slug"] for c in cmd_components(cfg, project)]
    with ThreadPoolExecutor(max_workers=8) as pool:      # ~30 components: 46s -> ~3s
        return list(pool.map(lambda s: component_stats(cfg, project, s, lang), slugs))


def push_branch_info(cfg, project, component):
    c = api_get(cfg, "components/%s/%s/" % (project, component))
    return {"repo": c["repo"], "branch": c["branch"],
            "push_branch": c.get("push_branch") or c["branch"]}


def main():
    import argparse
    p = argparse.ArgumentParser(prog="weblate_api.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("components").add_argument("project")
    st = sub.add_parser("stats"); st.add_argument("project"); st.add_argument("lang")
    pb = sub.add_parser("push-branch"); pb.add_argument("project"); pb.add_argument("component")
    mu = sub.add_parser("mr-url"); mu.add_argument("project"); mu.add_argument("component")
    args = p.parse_args()
    cfg = load_config()
    if args.cmd == "components":
        result = cmd_components(cfg, args.project)
    elif args.cmd == "stats":
        result = cmd_stats(cfg, args.project, args.lang)
    elif args.cmd == "push-branch":
        result = push_branch_info(cfg, args.project, args.component)
    else:
        info = push_branch_info(cfg, args.project, args.component)
        result = {"url": construct_mr_url(info["repo"], info["push_branch"], info["branch"])}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
