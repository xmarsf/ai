#!/usr/bin/env python3
"""GitLab CI driver for odoo-deploy: push, open MR, wait on webhook-delivered
pipeline status, fetch failed-job logs, local ruff, setup/check-setup.
Stdlib only. Every command prints exactly one JSON line on stdout."""
from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Some GitLab/WAF deployments reject the default Python-urllib agent with 403.
USER_AGENT = "odoo-deploy/1.0"
RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_BACKOFFS = (2, 5)  # seconds before attempt 2, then attempt 3
REQUIRED_CONFIG_KEYS = ("git_root", "gitlab_url")


def skill_dir() -> Path:
    """This skill's own base directory, resolved through a symlink."""
    return Path(__file__).resolve().parent.parent


def events_dir() -> Path:
    return skill_dir() / "docker" / "events"


def find_project_config(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        p = candidate / "config" / "project.json"
        if p.is_file():
            return p
    return None


def load_project_config() -> dict:
    path = find_project_config(Path.cwd())
    if path is None:
        raise SystemExit("error: no config/project.json found (walked up from cwd); "
                          "run 'odoo setup' first")
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_CONFIG_KEYS if not data.get(k)]
    if missing:
        raise SystemExit(f"error: {path} is missing {missing}; "
                          f"run 'odoo setup --force' (odoo-cli)")
    return data


_SSH_REMOTE_RE = re.compile(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?$")
_HTTPS_REMOTE_RE = re.compile(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?$")


def parse_remote_url(url: str) -> tuple[str, str]:
    """(host, project_path) from an SSH or HTTPS git remote URL."""
    match = _HTTPS_REMOTE_RE.match(url) or _SSH_REMOTE_RE.match(url)
    if not match:
        raise SystemExit(f"error: cannot parse git remote URL: {url}")
    return match.group(1), match.group(2)


def git_remote_project_path(remote: str, git_root: str) -> str | None:
    result = subprocess.run(["git", "remote", "get-url", remote],
                             cwd=git_root, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    _host, project_path = parse_remote_url(result.stdout.strip())
    return project_path


GITLAB_TOKEN_FILE = "~/.gitlab"


def _load_gitlab_token_file(path: str) -> dict[str, str]:
    cp = configparser.ConfigParser(delimiters=('=',))
    if not cp.read(os.path.expanduser(path)) or not cp.has_section("gitlab"):
        return {}
    return {opt.strip().rstrip("/") + "/": val.strip() for opt, val in cp.items("gitlab")}


def _git_credential_token(host: str) -> str | None:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(["git", "credential", "fill"],
                             input=f"protocol=https\nhost={host}\n\n",
                             capture_output=True, text=True, env=env)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    return None


def resolve_gitlab_token(host: str) -> str:
    tokens = _load_gitlab_token_file(GITLAB_TOKEN_FILE)
    token = tokens.get("https://" + host + "/")
    if token:
        return token
    token = _git_credential_token(host)
    if token:
        return token
    raise SystemExit(f"error: no GitLab token for {host} in ~/.gitlab and "
                      f"'git credential fill' returned none")


def api_request(token: str, method: str, url: str, data: dict | None = None,
                 timeout: int = 30) -> dict:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Authorization": "Bearer " + token, "User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    idempotent = method in ("GET", "DELETE")
    attempts = 0
    while True:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if idempotent and e.code in RETRY_STATUSES and attempts < len(RETRY_BACKOFFS):
                time.sleep(RETRY_BACKOFFS[attempts])
                attempts += 1
                continue
            detail = e.read().decode("utf-8", errors="replace")
            raise SystemExit(f"error: GitLab API {method} {url} returned {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempts < len(RETRY_BACKOFFS):
                time.sleep(RETRY_BACKOFFS[attempts])
                attempts += 1
                continue
            raise SystemExit(f"error: GitLab API {method} {url} unreachable: {e}")


PROTECTED_BRANCHES = {"dev", "main", "master", "production"}


def current_branch(git_root: str) -> str:
    return subprocess.run(["git", "branch", "--show-current"], cwd=git_root,
                           capture_output=True, text=True, check=True).stdout.strip()


def has_tracked_changes(git_root: str) -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=git_root,
                          capture_output=True, text=True, check=True).stdout
    return any(line and not line.startswith("??") for line in out.splitlines())


def rev_parse(git_root: str, ref: str) -> str | None:
    result = subprocess.run(["git", "rev-parse", ref], cwd=git_root,
                             capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def rebase_onto(git_root: str, upstream_ref: str) -> list[str] | None:
    """None on success; on conflict, aborts the rebase and returns the
    conflicting file paths."""
    result = subprocess.run(["git", "rebase", upstream_ref], cwd=git_root,
                             capture_output=True, text=True)
    if result.returncode == 0:
        return None
    conflicts = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=git_root, capture_output=True, text=True).stdout.split()
    subprocess.run(["git", "rebase", "--abort"], cwd=git_root, capture_output=True, text=True)
    return conflicts


def gitlab_project_id(token: str, gitlab_url: str, project_path: str) -> int:
    encoded = urllib.parse.quote(project_path, safe="")
    data = api_request(token, "GET", f"{gitlab_url}/api/v4/projects/{encoded}")
    return data["id"]


def find_open_mr(token: str, gitlab_url: str, upstream_id: int, fork_id: int,
                  branch: str, target: str) -> dict | None:
    q = urllib.parse.urlencode({"source_branch": branch, "target_branch": target,
                                 "state": "opened"})
    mrs = api_request(token, "GET",
                       f"{gitlab_url}/api/v4/projects/{upstream_id}/merge_requests?{q}")
    for mr in mrs:
        if mr.get("source_project_id") == fork_id:
            return mr
    return None


def oldest_commit_subjects(git_root: str, target: str) -> list[str]:
    out = subprocess.run(
        ["git", "log", "--reverse", "--format=%s", f"upstream/{target}..HEAD"],
        cwd=git_root, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def create_mr(token: str, gitlab_url: str, fork_id: int, upstream_id: int,
              branch: str, target: str, title: str, subjects: list[str]) -> dict:
    data = {
        "source_branch": branch,
        "target_branch": target,
        "target_project_id": upstream_id,
        "title": title,
        "description": "\n".join(f"- {s}" for s in subjects),
    }
    return api_request(token, "POST",
                        f"{gitlab_url}/api/v4/projects/{fork_id}/merge_requests", data=data)


def push_ref(git_root: str, branch: str, no_rebase: bool):
    args = ["git", "push"]
    if not no_rebase:
        args.append("--force-with-lease")
    args += ["origin", f"HEAD:{branch}"]
    return subprocess.run(args, cwd=git_root, capture_output=True, text=True)


def cmd_push(target: str = "dev", title: str | None = None, no_rebase: bool = False) -> dict:
    cfg = load_project_config()
    git_root = cfg["git_root"]
    gitlab_url = cfg["gitlab_url"]
    branch = current_branch(git_root)

    if has_tracked_changes(git_root):
        raise SystemExit("error: tracked files have staged or unstaged changes; "
                          "commit or stash first")
    if branch in PROTECTED_BRANCHES or branch == target:
        raise SystemExit(f"error: refusing to push protected/target branch {branch!r}")

    if not no_rebase:
        subprocess.run(["git", "fetch", "upstream", target], cwd=git_root,
                        check=True, capture_output=True, text=True)
        conflicts = rebase_onto(git_root, f"upstream/{target}")
        if conflicts is not None:
            print(json.dumps({"conflicts": conflicts}, ensure_ascii=False))
            raise SystemExit(4)

    sha = rev_parse(git_root, "HEAD")
    origin_sha = rev_parse(git_root, f"origin/{branch}")
    out: dict = {"sha": sha}
    if origin_sha == sha:
        out["pushed"] = False
    else:
        since = time.time_ns()
        result = push_ref(git_root, branch, no_rebase)
        if result.returncode != 0:
            print(json.dumps({"error": result.stderr.strip()}, ensure_ascii=False))
            raise SystemExit(5)
        out["pushed"] = True
        out["since"] = since

    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    upstream_path = git_remote_project_path("upstream", git_root)
    fork_path = git_remote_project_path("origin", git_root)
    upstream_id = gitlab_project_id(token, gitlab_url, upstream_path)
    fork_id = gitlab_project_id(token, gitlab_url, fork_path)

    mr = find_open_mr(token, gitlab_url, upstream_id, fork_id, branch, target)
    if mr is None:
        subjects = oldest_commit_subjects(git_root, target)
        mr_title = title or (subjects[0] if subjects else branch)
        mr = create_mr(token, gitlab_url, fork_id, upstream_id, branch, target, mr_title, subjects)

    out["mr_url"] = mr["web_url"]
    out["mr_iid"] = mr["iid"]
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gitlab_ci.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    push = sub.add_parser("push")
    push.add_argument("--target", default="dev")
    push.add_argument("--title")
    push.add_argument("--no-rebase", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "push":
            result = cmd_push(target=args.target, title=args.title, no_rebase=args.no_rebase)
        else:  # pragma: no cover - argparse already rejects unknown subcommands
            raise SystemExit("error: unknown command %r" % args.cmd)
    except SystemExit as e:
        if isinstance(e.code, int):
            return e.code
        print(str(e.code), file=sys.stderr)
        return 10
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
