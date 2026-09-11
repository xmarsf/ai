#!/usr/bin/env python3
"""GitLab CI driver for odoo-deploy: push, open MR, wait on webhook-delivered
pipeline status, fetch failed-job logs, local ruff, setup/check-setup.
Stdlib only. Every command prints exactly one JSON line on stdout."""
from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
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
