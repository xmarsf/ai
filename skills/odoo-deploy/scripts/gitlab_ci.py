#!/usr/bin/env python3
"""GitLab CI driver for odoo-deploy: push, open MR, wait on webhook-delivered
pipeline status, fetch failed-job logs, local ruff, setup/check-setup.
Stdlib only. Every command prints exactly one JSON line on stdout."""
from __future__ import annotations

import argparse
import configparser
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
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


FINAL_STATUSES = {"success", "failed", "canceled", "skipped"}
EXIT_BY_STATUS = {"success": 0, "failed": 1, "canceled": 2, "skipped": 2}
NO_PIPELINE_SECONDS = 600


def _iso_to_ns(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1_000_000_000)


def _counts(status: str | None, finished_at: str | None, since: int | None) -> bool:
    if status not in FINAL_STATUSES:
        return False
    if since is None:
        return True
    if not finished_at:
        return False
    return _iso_to_ns(finished_at) >= since


def _scan_events(mr_iid: int, sha: str, since: int | None) -> list[dict]:
    ev_dir = events_dir()
    if not ev_dir.is_dir():
        return []
    matches = []
    for path in sorted(ev_dir.rglob("*.json")):
        try:
            received_ns = int(path.stem)
        except ValueError:
            continue
        if since is not None and received_ns < since:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mr = data.get("merge_request") or {}
        attrs = data.get("object_attributes") or {}
        if mr.get("iid") == mr_iid and attrs.get("sha") == sha:
            matches.append(data)
    return matches


def cmd_wait(mr_iid: int, sha: str, since: int | None = None, timeout_minutes: int = 120,
             sleep_fn=time.sleep, now_fn=time.time) -> dict:
    cfg = load_project_config()
    gitlab_url = cfg["gitlab_url"]
    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    upstream_path = git_remote_project_path("upstream", cfg["git_root"])
    upstream_id = gitlab_project_id(token, gitlab_url, upstream_path)

    mr = api_request(token, "GET",
                      f"{gitlab_url}/api/v4/projects/{upstream_id}/merge_requests/{mr_iid}")
    head = mr.get("head_pipeline") or {}
    pipeline_exists = head.get("sha") == sha
    if pipeline_exists and _counts(head.get("status"), head.get("finished_at"), since):
        return {"pipeline_id": head["id"], "project_id": head["project_id"],
                "status": head["status"], "web_url": head["web_url"]}

    deadline = now_fn() + timeout_minutes * 60
    no_pipeline_deadline = now_fn() + NO_PIPELINE_SECONDS
    while True:
        if now_fn() >= deadline:
            print(json.dumps({"reason": "timeout"}, ensure_ascii=False))
            raise SystemExit(3)
        if not pipeline_exists and now_fn() >= no_pipeline_deadline:
            print(json.dumps({"reason": "no_pipeline"}, ensure_ascii=False))
            raise SystemExit(3)

        events = _scan_events(mr_iid, sha, since)
        if events:
            pipeline_exists = True
        for event in events:
            attrs = event.get("object_attributes") or {}
            if attrs.get("status") not in FINAL_STATUSES:
                continue
            project_id = (event.get("project") or {}).get("id")
            pipeline_id = attrs.get("id")
            pipeline = api_request(token, "GET",
                                    f"{gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}")
            if _counts(pipeline.get("status"), pipeline.get("finished_at"), since):
                return {"pipeline_id": pipeline_id, "project_id": project_id,
                        "status": pipeline["status"], "web_url": pipeline["web_url"]}

        sleep_fn(5)


def api_request_raw(token: str, url: str, timeout: int = 60) -> bytes:
    headers = {"Authorization": "Bearer " + token, "User-Agent": USER_AGENT}
    attempts = 0
    while True:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUSES and attempts < len(RETRY_BACKOFFS):
                time.sleep(RETRY_BACKOFFS[attempts])
                attempts += 1
                continue
            raise SystemExit(f"error: GitLab API GET {url} returned {e.code}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempts < len(RETRY_BACKOFFS):
                time.sleep(RETRY_BACKOFFS[attempts])
                attempts += 1
                continue
            raise SystemExit(f"error: GitLab API GET {url} unreachable: {e}")


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TRACE_PREFIX_RE = re.compile(r"^\S+Z \d+[OE]\+? ")


def _clean_trace(raw: bytes) -> str:
    lines = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = ANSI_RE.sub("", line)
        line = TRACE_PREFIX_RE.sub("", line)
        lines.append(line)
    return "\n".join(lines) + "\n"


def _safe_extract(zip_bytes: bytes, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if target != dest and dest not in target.parents:
                raise SystemExit(f"error: artifact zip entry escapes destination: {member.filename}")
        zf.extractall(dest)


def cmd_fetch_logs(project_id: int, pipeline_id: int, out_dir: str) -> dict:
    cfg = load_project_config()
    gitlab_url = cfg["gitlab_url"]
    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    jobs = api_request(token, "GET",
                        f"{gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}"
                        f"/jobs?per_page=100")
    manifest = []
    for job in jobs:
        if job.get("status") != "failed" or job.get("allow_failure"):
            continue
        trace_raw = api_request_raw(
            token, f"{gitlab_url}/api/v4/projects/{project_id}/jobs/{job['id']}/trace")
        trace_path = out / f"{job['name']}.log"
        trace_path.write_text(_clean_trace(trace_raw), encoding="utf-8")

        artifacts = None
        if any(a.get("file_type") == "archive" for a in job.get("artifacts") or []):
            zip_bytes = api_request_raw(
                token, f"{gitlab_url}/api/v4/projects/{project_id}/jobs/{job['id']}/artifacts")
            artifacts_dir = out / job["name"]
            _safe_extract(zip_bytes, artifacts_dir)
            artifacts = str(artifacts_dir)

        manifest.append({"job": job["name"], "stage": job.get("stage"),
                          "failure_reason": job.get("failure_reason"),
                          "trace": str(trace_path), "artifacts": artifacts})

    return {"jobs": manifest}


def parse_ci_config_path(raw: str) -> tuple[str, str, str]:
    """'<file>@<project>:<ref>' -> (file, project_path, ref)."""
    match = re.match(r"^(?P<file>[^@]+)@(?P<project>[^:]+):(?P<ref>.+)$", raw)
    if not match:
        raise SystemExit(f"error: cannot parse ci_config_path: {raw!r}")
    return match.group("file"), match.group("project"), match.group("ref")


def repo_file_raw(token: str, gitlab_url: str, project_id: int, ref: str, file_path: str) -> str:
    encoded_path = urllib.parse.quote(file_path, safe="")
    encoded_ref = urllib.parse.quote(ref, safe="")
    url = (f"{gitlab_url}/api/v4/projects/{project_id}/repository/files/"
           f"{encoded_path}/raw?ref={encoded_ref}")
    return api_request_raw(token, url).decode("utf-8")


def _yaml_scalar(text: str, key: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(key)}\s*:\s*["\']?([^"\'\n]*?)["\']?\s*$',
                       text, re.MULTILINE)
    return match.group(1).strip() if match else None


def rewrite_ruff_ignore(ruff_toml_text: str, ignore_linters: str) -> str:
    """Replace the `extend-exclude` line to match CI's own
    scripts/utils.sh get_ignore_file_command_ruff — confirmed against the
    real script in Step 3 above."""
    modules = [m.strip() for m in ignore_linters.split(",") if m.strip()]
    patterns = ", ".join(f'"{m}/**"' for m in modules)
    replacement = f"extend-exclude = [{patterns}]"
    new_text, count = re.subn(r"^extend-exclude\s*=\s*\[.*?\]", replacement, ruff_toml_text,
                               count=1, flags=re.MULTILINE | re.DOTALL)
    if count == 0:
        return ruff_toml_text.rstrip("\n") + "\n" + replacement + "\n"
    return new_text


def cmd_lint(target: str = "dev") -> dict:
    cfg = load_project_config()
    git_root, gitlab_url = cfg["git_root"], cfg["gitlab_url"]
    addons_dir = cfg["addons_dir"]
    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    upstream_path = git_remote_project_path("upstream", git_root)
    upstream_id = gitlab_project_id(token, gitlab_url, upstream_path)

    project = api_request(token, "GET", f"{gitlab_url}/api/v4/projects/{upstream_id}")
    ci_config_path = project.get("ci_config_path")
    if not ci_config_path:
        raise SystemExit("error: upstream project has no ci_config_path")
    ci_file, template_path, ref = parse_ci_config_path(ci_config_path)
    template_id = gitlab_project_id(token, gitlab_url, template_path)

    ci_yaml = repo_file_raw(token, gitlab_url, template_id, ref, ci_file)
    enable_ruff = _yaml_scalar(ci_yaml, "ENABLE_RUFF")
    if enable_ruff != "true":
        return {"skipped": True}
    ignore_linters = _yaml_scalar(ci_yaml, "IGNORE_LINTERS") or ""

    dockerfile = repo_file_raw(token, gitlab_url, template_id, ref,
                                "config/docker/Dockerfile.cicd-runner")
    version_match = re.search(r"ruff==([0-9][0-9.]*)", dockerfile)
    ruff_toml = repo_file_raw(token, gitlab_url, template_id, ref,
                               "config/linters/ruff/ruff.toml")
    if version_match is None or not ruff_toml.strip():
        raise SystemExit("error: could not parse ruff version or ruff.toml from CI template")
    ruff_version = version_match.group(1)

    rewritten = rewrite_ruff_ignore(ruff_toml, ignore_linters)
    fd, tmp_path = tempfile.mkstemp(suffix=".toml")
    os.close(fd)
    tmp_config = Path(tmp_path)
    tmp_config.write_text(rewritten, encoding="utf-8")
    try:
        try:
            result = subprocess.run(
                ["uvx", f"ruff@{ruff_version}", "check", "--config", str(tmp_config),
                 "--output-format", "json", addons_dir],
                capture_output=True, text=True)
        except FileNotFoundError:
            raise SystemExit("error: uvx not found; install with 'pipx install uv' or similar")
        try:
            raw_findings = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as e:
            raise SystemExit(f"error: ruff output was not valid JSON: {e}")
    finally:
        tmp_config.unlink(missing_ok=True)
    changed = set(subprocess.run(
        ["git", "diff", "--name-only", f"upstream/{target}...HEAD"],
        cwd=git_root, capture_output=True, text=True).stdout.splitlines())

    findings = [{"file": f["filename"], "line": f["location"]["row"], "rule": f["code"],
                 "message": f["message"],
                 "in_branch": os.path.relpath(f["filename"], git_root) in changed}
                for f in raw_findings]

    payload = {"ruff_version": ruff_version, "findings": findings}
    if findings:
        print(json.dumps(payload, ensure_ascii=False))
        raise SystemExit(1)
    return payload


def cmd_retry_job(project_id: int, job_id: int) -> dict:
    cfg = load_project_config()
    gitlab_url = cfg["gitlab_url"]
    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    since = time.time_ns()
    new_job = api_request(token, "POST",
                           f"{gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}/retry")
    return {"job_id": new_job["id"], "pipeline_id": new_job["pipeline"]["id"], "since": since}


TELEGRAM_API_BASE = "https://api.telegram.org"


def cmd_notify(text: str) -> dict:
    cfg = load_project_config()
    channel, token = cfg.get("telegram_channel"), cfg.get("telegram_token")
    if not channel or not token:
        return {"telegram": "failed: no telegram_channel/telegram_token in config/project.json"}
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    body = json.dumps({"chat_id": channel, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"telegram": f"failed: HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"telegram": f"failed: {e}"}
    if not result.get("ok"):
        return {"telegram": f"failed: {result.get('description', result)}"}
    return {"telegram": "sent"}


def cmd_clean(mr_iid: int) -> dict:
    ev_dir = events_dir()
    removed = []
    if not ev_dir.is_dir():
        return {"removed": removed}
    for project_dir in ev_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for pipeline_dir in project_dir.iterdir():
            if not pipeline_dir.is_dir():
                continue
            matches = False
            for event_file in pipeline_dir.glob("*.json"):
                try:
                    data = json.loads(event_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if (data.get("merge_request") or {}).get("iid") == mr_iid:
                    matches = True
                    break
            if matches:
                shutil.rmtree(pipeline_dir)
                removed.append(int(pipeline_dir.name))
    return {"removed": removed}


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

    wait = sub.add_parser("wait")
    wait.add_argument("--mr", type=int, required=True, dest="mr_iid")
    wait.add_argument("--sha", required=True)
    wait.add_argument("--since", type=int)
    wait.add_argument("--timeout", type=int, default=120)

    fetch_logs = sub.add_parser("fetch-logs")
    fetch_logs.add_argument("--project", type=int, required=True, dest="project_id")
    fetch_logs.add_argument("--pipeline", type=int, required=True, dest="pipeline_id")
    fetch_logs.add_argument("--out", required=True, dest="out_dir")

    lint = sub.add_parser("lint")
    lint.add_argument("--target", default="dev")

    retry_job = sub.add_parser("retry-job")
    retry_job.add_argument("--project", type=int, required=True, dest="project_id")
    retry_job.add_argument("--job", type=int, required=True, dest="job_id")

    notify = sub.add_parser("notify")
    notify.add_argument("--text", required=True)

    clean = sub.add_parser("clean")
    clean.add_argument("--mr", type=int, required=True, dest="mr_iid")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "push":
            result = cmd_push(target=args.target, title=args.title, no_rebase=args.no_rebase)
        elif args.cmd == "wait":
            result = cmd_wait(mr_iid=args.mr_iid, sha=args.sha, since=args.since,
                               timeout_minutes=args.timeout)
        elif args.cmd == "fetch-logs":
            result = cmd_fetch_logs(project_id=args.project_id, pipeline_id=args.pipeline_id,
                                     out_dir=args.out_dir)
        elif args.cmd == "lint":
            result = cmd_lint(target=args.target)
        elif args.cmd == "retry-job":
            result = cmd_retry_job(project_id=args.project_id, job_id=args.job_id)
        elif args.cmd == "notify":
            result = cmd_notify(text=args.text)
        elif args.cmd == "clean":
            result = cmd_clean(mr_iid=args.mr_iid)
        else:  # pragma: no cover - argparse already rejects unknown subcommands
            raise SystemExit("error: unknown command %r" % args.cmd)
    except SystemExit as e:
        if isinstance(e.code, int):
            return e.code
        print(str(e.code), file=sys.stderr)
        return 10
    print(json.dumps(result, ensure_ascii=False))
    if args.cmd == "wait":
        return EXIT_BY_STATUS.get(result.get("status"), 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
