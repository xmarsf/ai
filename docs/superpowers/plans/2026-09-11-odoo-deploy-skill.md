# odoo-deploy Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `odoo-deploy` skill — after implementation work is
committed and verified, one skill pushes the branch, opens/reuses the MR,
learns the pipeline result through a GitLab webhook delivered via a
Cloudflare tunnel, and loops fix→push→wait until the pipeline is green or an
escalation rule fires.

**Architecture:** One stdlib-only CLI, `scripts/gitlab_ci.py`, exposing one
subcommand per unit of work (`push`, `wait`, `fetch-logs`, `lint`,
`retry-job`, `notify`, `clean`, `setup`, `check-setup`); each command prints
exactly one JSON line on stdout, mirroring `skills/odoo-wlc/scripts/weblate_api.py`.
A Docker Compose pair (`cloudflared` + `listener.py`, a stdlib
`http.server` webhook receiver) runs `restart: unless-stopped` and writes one
file per pipeline-webhook delivery under `docker/events/`; `wait` reads that
directory instead of polling GitLab. `SKILL.md` sequences the commands into
the offer→setup-gate→preflight→push→wait→(green|red loop) flow described in
the spec; `README.md` is the one-time human setup guide every `check-setup`
failure's `fix` field points into.

**Tech Stack:** Python 3.12 stdlib only (`urllib`, `subprocess`,
`http.server`, `json`, `configparser`, `zipfile`, `hmac`, `secrets`,
`argparse`); Docker Compose v2 (`cloudflared` + `python:3.12-slim`); pytest,
same style as `skills/odoo-wlc/tests/test_weblate_api.py` (`urlopen`
monkeypatched, `subprocess` mocked for `git credential`/`docker`/`uvx`, time
injected, no real sleeping) plus a real-server test file for the listener;
`uvx` for pinned-version `ruff` runs; Telegram Bot API for `notify`.

**Spec:** `docs/superpowers/specs/2026-09-11-odoo-deploy-design.md`

## Global Constraints

- Stdlib only in both `scripts/gitlab_ci.py` and `docker/listener.py` — no
  new pip dependency anywhere in this skill.
- Every `gitlab_ci.py` command prints **exactly one JSON line** on stdout
  (`json.dumps(result, ensure_ascii=False)`, no `indent=` — one line).
- Every HTTP request (GitLab API, Telegram API) sends a non-default
  `User-Agent` — a bare `Python-urllib/3.x` gets 403'd by some deployments'
  WAF (see `weblate_api.py`'s `USER_AGENT` comment; the GitLab instance here
  is not yet proven to need it, but the pattern costs nothing and the spec
  requires it verbatim: "HTTP requests send a non-default `User-Agent`").
- HTTP retry policy (GitLab API only): up to 3 attempts total, 2s then 5s
  backoff, on connection/DNS errors, timeouts, HTTP 429, and HTTP 5xx. Other
  4xx fail immediately, no retry. A POST/PUT is retried **only** when no
  response arrived at all (connection/DNS/timeout) — never after an HTTP
  response, even a 5xx, so a lost reply never risks a duplicate MR or a
  double retry-job.
- GitLab auth: `Authorization: Bearer <token>` header, resolved from
  `~/.gitlab`'s `[gitlab]` section by host, else `git credential fill`
  (`GIT_TERMINAL_PROMPT=0`), else exit 10. Never printed.
- Tokens and secrets (`WEBHOOK_SECRET`, GitLab token, Telegram token) are
  never written to stdout/stderr by any command.
- `gitlab_ci.py` never merges, approves, or enables auto-merge on any MR —
  no such command exists in this script, ever (No-merge rule).
- Exit codes (verbatim from spec, apply across all commands):

  | Code | Meaning |
  |---|---|
  | 0 | ok / pipeline `success` / no lint findings |
  | 1 | pipeline `failed` / lint findings |
  | 2 | pipeline `canceled` or `skipped` |
  | 3 | no pipeline for `SHA` within 10 min, or `--timeout` elapsed (`reason` says which) |
  | 4 | rebase conflict (rebase aborted) |
  | 5 | push rejected |
  | 10 | usage, config, auth, or API error (message on stderr) |
  | 11 | setup incomplete (`check-setup` JSON lists failed checks and fixes) |

- `SKILL_DIR` resolution: every script path in `SKILL.md` is
  `$SKILL_DIR/scripts/...`, where `SKILL_DIR` is this skill's own base
  directory (works whether the skill is symlinked under `~/.claude/skills` or
  checked into a project repo directly) — same convention as
  `skills/odoo-wlc/SKILL.md`'s "Resolve the skill directory first" section.
  Inside `gitlab_ci.py` itself, paths resolve from `Path(__file__).resolve()`,
  which works identically through a symlink.

---

### Task 1: Config, git-remote, and GitLab-HTTP helpers

**Files:**
- Create: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `load_project_config() -> dict` (reads `config/project.json` by
  walking up from `Path.cwd()`, requires `git_root`+`gitlab_url`, else
  `SystemExit`); `parse_remote_url(url: str) -> tuple[str, str]` (host,
  project-path); `git_remote_project_path(remote: str, git_root: str) ->
  str | None`; `resolve_gitlab_token(host: str) -> str`;
  `api_request(token: str, method: str, url: str, data: dict | None = None)
  -> dict`. Later tasks (`push`, `wait`, ...) call all five.
- Consumes: nothing from other tasks (this is the foundation task).

- [ ] **Step 1: Write the failing tests for config loading**

Create `skills/odoo-deploy/tests/test_gitlab_ci.py`:

```python
import io
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gitlab_ci


def _write_project_config(root: Path, **fields) -> Path:
    base = {"git_root": str(root / "repo"), "gitlab_url": "https://gitlab.vdx.vn"}
    base.update(fields)
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "project.json").write_text(json.dumps(base), encoding="utf-8")
    return cfg_dir / "project.json"


def test_load_project_config_walks_up(tmp_path, monkeypatch):
    _write_project_config(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    cfg = gitlab_ci.load_project_config()
    assert cfg["git_root"] == str(tmp_path / "repo")
    assert cfg["gitlab_url"] == "https://gitlab.vdx.vn"


def test_load_project_config_missing_file_exits_10(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try:
        gitlab_ci.load_project_config()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code != 0


def test_load_project_config_missing_required_key_exits(tmp_path, monkeypatch):
    _write_project_config(tmp_path, gitlab_url="")
    monkeypatch.chdir(tmp_path)
    try:
        gitlab_ci.load_project_config()
        assert False, "expected SystemExit"
    except SystemExit:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gitlab_ci'`.

- [ ] **Step 3: Write the config-loading implementation**

Create `skills/odoo-deploy/scripts/gitlab_ci.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify config-loading tests pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing tests for remote-URL parsing**

Append to `tests/test_gitlab_ci.py`:

```python
def test_parse_remote_url_https():
    assert gitlab_ci.parse_remote_url("https://gitlab.vdx.vn/sungroup/sca") == \
        ("gitlab.vdx.vn", "sungroup/sca")


def test_parse_remote_url_https_with_git_suffix():
    assert gitlab_ci.parse_remote_url("https://gitlab.vdx.vn/truong/sca.git") == \
        ("gitlab.vdx.vn", "truong/sca")


def test_parse_remote_url_ssh_scp_form():
    assert gitlab_ci.parse_remote_url("git@gitlab.vdx.vn:sungroup/sca.git") == \
        ("gitlab.vdx.vn", "sungroup/sca")


def test_parse_remote_url_ssh_url_form():
    assert gitlab_ci.parse_remote_url("ssh://git@gitlab.vdx.vn/sungroup/sca.git") == \
        ("gitlab.vdx.vn", "sungroup/sca")


def test_git_remote_project_path_reads_git_remote(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(args, 0, stdout="https://gitlab.vdx.vn/sungroup/sca\n", stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    assert gitlab_ci.git_remote_project_path("upstream", "/repo") == "sungroup/sca"
    assert seen["args"] == ["git", "remote", "get-url", "upstream"]
    assert seen["cwd"] == "/repo"


def test_git_remote_project_path_none_when_remote_missing(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="error: No such remote")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    assert gitlab_ci.git_remote_project_path("upstream", "/repo") is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'parse_remote_url'`.

- [ ] **Step 7: Implement remote-URL parsing**

Add to `scripts/gitlab_ci.py`, after `load_project_config`:

```python
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
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (9 tests).

- [ ] **Step 9: Write the failing tests for token resolution**

Append to `tests/test_gitlab_ci.py`:

```python
GITLAB_INI = "[gitlab]\nhttps://gitlab.vdx.vn/ = FILETOKEN\n"


def test_resolve_gitlab_token_from_file(tmp_path, monkeypatch):
    ini = tmp_path / "gitlab"
    ini.write_text(GITLAB_INI, encoding="utf-8")
    monkeypatch.setattr(gitlab_ci, "GITLAB_TOKEN_FILE", str(ini))
    assert gitlab_ci.resolve_gitlab_token("gitlab.vdx.vn") == "FILETOKEN"


def test_resolve_gitlab_token_falls_back_to_git_credential(tmp_path, monkeypatch):
    ini = tmp_path / "nope"
    monkeypatch.setattr(gitlab_ci, "GITLAB_TOKEN_FILE", str(ini))

    def fake_run(args, **kwargs):
        assert args == ["git", "credential", "fill"]
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["input"] == "protocol=https\nhost=gitlab.vdx.vn\n\n"
        return subprocess.CompletedProcess(args, 0, stdout="password=CREDTOKEN\n", stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    assert gitlab_ci.resolve_gitlab_token("gitlab.vdx.vn") == "CREDTOKEN"


def test_resolve_gitlab_token_neither_exits_10(tmp_path, monkeypatch):
    monkeypatch.setattr(gitlab_ci, "GITLAB_TOKEN_FILE", str(tmp_path / "nope"))

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    try:
        gitlab_ci.resolve_gitlab_token("gitlab.vdx.vn")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "no GitLab token" in str(e.code)
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'resolve_gitlab_token'`.

- [ ] **Step 11: Implement token resolution**

Add to `scripts/gitlab_ci.py`, after `git_remote_project_path`:

```python
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
```

Every helper in this script raises `SystemExit("error: ...")` — message
only, so Python's default exit code (1) applies when the module is imported
as a library (as the tests do) or run standalone. `main()` (Task 7) wraps
the whole dispatch in `try/except SystemExit` and re-exits with code 10 for
any string-valued `SystemExit`, which is how the spec's "usage, config,
auth, or API error" row (exit 10) is satisfied without every helper needing
to know its own final exit code. Commands with their own specific exit codes
(`push`, `wait`, `lint`, ...) raise `SystemExit(N)` with an **int** instead —
`main()` passes those through unchanged (see Task 7). `load_project_config`'s
two `SystemExit(f"error: ...")` calls in Step 3 already follow this same
message-only convention, as does Step 9's `test_resolve_gitlab_token_neither_exits_10`.

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (12 tests).

- [ ] **Step 13: Write the failing tests for the HTTP retry policy**

Add `import urllib.error` to the top of `tests/test_gitlab_ci.py`, next to
the existing `import io` / `import json` imports.

Append to `tests/test_gitlab_ci.py`:

```python
def _http_error(url, code, body=b"{}"):
    return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(body))


def test_api_request_get_success(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert req.headers["User-agent"] == gitlab_ci.USER_AGENT
        assert req.headers["Authorization"] == "Bearer TOK"
        return io.BytesIO(b'{"id": 1}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    assert gitlab_ci.api_request("TOK", "GET", "https://x/api/v4/y") == {"id": 1}


def test_api_request_retries_connection_error_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("dns failure")
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: sleeps.append(s))
    assert gitlab_ci.api_request("TOK", "GET", "https://x/y") == {"ok": True}
    assert calls["n"] == 3
    assert sleeps == [2, 5]


def test_api_request_retries_5xx_and_429_for_get(monkeypatch):
    codes = iter([503, 429])
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        try:
            code = next(codes)
        except StopIteration:
            return io.BytesIO(b'{"ok": true}')
        raise _http_error(req.full_url, code)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    assert gitlab_ci.api_request("TOK", "GET", "https://x/y") == {"ok": True}
    assert calls["n"] == 3


def test_api_request_other_4xx_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(req.full_url, 404)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    try:
        gitlab_ci.api_request("TOK", "GET", "https://x/y")
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert calls["n"] == 1


def test_api_request_post_not_retried_after_http_response(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(req.full_url, 500)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    try:
        gitlab_ci.api_request("TOK", "POST", "https://x/y", data={"a": 1})
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert calls["n"] == 1  # a 500 IS a response — never retried for POST


def test_api_request_post_retried_on_connection_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("connection refused")
        return io.BytesIO(b'{"id": 5}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    assert gitlab_ci.api_request("TOK", "POST", "https://x/y", data={"a": 1}) == {"id": 5}
    assert calls["n"] == 2
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'api_request'`.

- [ ] **Step 15: Implement `api_request`**

Add to `scripts/gitlab_ci.py`, after `resolve_gitlab_token`:

```python
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
```

- [ ] **Step 16: Run all Task 1 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (18 tests).

- [ ] **Step 17: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): config/git-remote/GitLab-HTTP helpers

Config loader walks up for config/project.json (git_root+gitlab_url
required); GitLab auth resolves from ~/.gitlab then git credential
fill; api_request implements the 3-attempt 2s/5s retry policy, with
POST/PUT retried only on no-response errors so a lost reply never
risks a duplicate write."
```

---

### Task 2: `push` command

**Files:**
- Modify: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `cmd_push(target: str, title: str | None, no_rebase: bool) -> dict`
  (the JSON-able result; `main()` prints it and sets the exit code) and a
  first `main()` with an argparse `push` subcommand — every later task adds
  one more subparser to this same `main()`.
- Consumes: `load_project_config`, `git_remote_project_path`,
  `resolve_gitlab_token`, `api_request`, `parse_remote_url` (all Task 1).

- [ ] **Step 1: Write the failing tests for the git-only push helpers**

Append to `tests/test_gitlab_ci.py`:

```python
def _bare(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
    return path


def _clone(bare: Path, into: Path, name: str = "origin") -> Path:
    subprocess.run(["git", "clone", "-q", str(bare), str(into)], check=True)
    subprocess.run(["git", "-C", str(into), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(into), "config", "user.name", "T"], check=True)
    return into


def _commit(repo: Path, filename: str, subject: str) -> None:
    (repo / filename).write_text(subject, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", subject], check=True)


def test_current_branch(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:main"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    assert gitlab_ci.current_branch(str(repo)) == "feature-x"


def test_has_tracked_changes_ignores_untracked(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    (repo / "untracked.txt").write_text("x", encoding="utf-8")
    assert gitlab_ci.has_tracked_changes(str(repo)) is False


def test_has_tracked_changes_true_for_staged_and_unstaged(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    assert gitlab_ci.has_tracked_changes(str(repo)) is True


def test_rebase_onto_success(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(repo, "b.txt", "feature work")
    other = _clone(bare, tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "dev"], check=True)
    _commit(other, "c.txt", "upstream work")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "upstream", str(bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "upstream", "dev"], check=True)

    assert gitlab_ci.rebase_onto(str(repo), "upstream/dev") is None
    assert (repo / "c.txt").is_file()  # upstream commit now in history


def test_rebase_onto_conflict_aborts_and_lists_files(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(repo, "a.txt", "feature change")
    other = _clone(bare, tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "dev"], check=True)
    _commit(other, "a.txt", "conflicting upstream change")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "upstream", str(bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "upstream", "dev"], check=True)

    conflicts = gitlab_ci.rebase_onto(str(repo), "upstream/dev")
    assert conflicts == ["a.txt"]
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                             capture_output=True, text=True).stdout
    assert status.strip() == ""  # rebase was aborted, tree is clean again
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "current_branch or has_tracked_changes or rebase_onto" -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 3: Implement the git-only push helpers**

Add to `scripts/gitlab_ci.py`, after `api_request`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "current_branch or has_tracked_changes or rebase_onto" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing tests for `cmd_push`**

Append to `tests/test_gitlab_ci.py`:

```python
def _push_setup(tmp_path, monkeypatch):
    """Fork (origin) + upstream bare repos, a working clone tracking origin,
    upstream added as a second remote, on branch feature-x with one commit
    ahead of upstream/dev. Returns (repo, upstream_bare)."""
    upstream_bare = _bare(tmp_path / "upstream.git")
    seed = _clone(upstream_bare, tmp_path / "seed")
    _commit(seed, "a.txt", "init")
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:dev"], check=True)

    fork_bare = _bare(tmp_path / "fork.git")
    subprocess.run(["git", "clone", "-q", "--bare", str(upstream_bare), str(fork_bare)],
                    check=False)  # fork starts equal to upstream; ignore if already bare-cloned

    repo = _clone(upstream_bare, tmp_path / "repo", name="upstream")
    subprocess.run(["git", "-C", str(repo), "remote", "rename", "upstream", "upstream"],
                    check=False)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(fork_bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(repo, "b.txt", "feature work")

    monkeypatch.chdir(repo)
    cfg_dir = repo / "config"
    cfg_dir.mkdir()
    (cfg_dir / "project.json").write_text(
        json.dumps({"git_root": str(repo), "gitlab_url": "https://gitlab.vdx.vn"}), encoding="utf-8")
    return repo, upstream_bare


def _stub_mr_api(monkeypatch, existing=None, created=None):
    calls = []

    def fake_api_request(token, method, url, data=None, **kw):
        calls.append((method, url, data))
        if method == "GET":
            return existing or []
        return created or {"iid": 1, "web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/1"}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id",
                         lambda token, gitlab_url, path: {"sungroup/sca": 21, "truong/sca": 90}[path])
    return calls


def test_cmd_push_refuses_dirty_tree(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    (repo / "b.txt").write_text("dirty", encoding="utf-8")
    try:
        gitlab_ci.cmd_push(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "tracked" in str(e.code) or "dirty" in str(e.code)


def test_cmd_push_refuses_protected_branch(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "dev"], check=True)
    try:
        gitlab_ci.cmd_push(target="dev")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_cmd_push_creates_mr_with_default_title(tmp_path, monkeypatch):
    repo, upstream_bare = _push_setup(tmp_path, monkeypatch)
    calls = _stub_mr_api(monkeypatch, existing=[], created={
        "iid": 7, "web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/7"})

    result = gitlab_ci.cmd_push(target="dev")

    assert result["mr_url"] == "https://gitlab.vdx.vn/g/p/-/merge_requests/7"
    assert result["mr_iid"] == 7
    assert result["pushed"] is True
    assert "since" in result
    post_calls = [c for c in calls if c[0] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0][2]["title"] == "feature work"
    assert post_calls[0][2]["description"] == "- feature work"
    assert post_calls[0][2]["target_project_id"] == 21
    assert "merge_when_pipeline_succeeds" not in post_calls[0][2]


def test_cmd_push_reuses_open_mr(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    calls = _stub_mr_api(monkeypatch, existing=[
        {"iid": 3, "web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/3",
         "source_project_id": 90}])

    result = gitlab_ci.cmd_push(target="dev")

    assert result["mr_iid"] == 3
    assert not [c for c in calls if c[0] == "POST"]  # never created a second MR


def test_cmd_push_no_push_when_origin_already_at_head(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:feature-x"], check=True)
    _stub_mr_api(monkeypatch, existing=[{"iid": 3, "web_url": "https://x/3", "source_project_id": 90}])

    result = gitlab_ci.cmd_push(target="dev")

    assert result["pushed"] is False
    assert "since" not in result


def test_cmd_push_rebase_conflict_exits_4(tmp_path, monkeypatch):
    repo, upstream_bare = _push_setup(tmp_path, monkeypatch)
    other = _clone(upstream_bare, tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "dev"], check=True)
    (other / "b.txt").write_text("conflicting upstream change", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "b.txt"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "upstream b.txt"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "dev"], check=True)

    try:
        gitlab_ci.cmd_push(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 4


def test_cmd_push_no_rebase_fast_forward_push(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    _stub_mr_api(monkeypatch, existing=[{"iid": 3, "web_url": "https://x/3", "source_project_id": 90}])

    result = gitlab_ci.cmd_push(target="dev", no_rebase=True)

    assert result["pushed"] is True
    fork_head = subprocess.run(["git", "-C", str(repo), "ls-remote", "origin", "feature-x"],
                                capture_output=True, text=True).stdout
    local_head = gitlab_ci.rev_parse(str(repo), "HEAD")
    assert local_head in fork_head


def test_cmd_push_non_fast_forward_exits_5(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    fork_bare = Path(subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True).stdout.strip())
    other = _clone(fork_bare, tmp_path / "other-fork-clone")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(other, "z.txt", "someone else pushed to the fork branch")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "feature-x"], check=True)

    try:
        gitlab_ci.cmd_push(target="dev", no_rebase=True)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 5
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k cmd_push -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'cmd_push'`.

- [ ] **Step 7: Implement `gitlab_project_id`, MR find/create, and `cmd_push`**

Add to `scripts/gitlab_ci.py`, after `rebase_onto`:

```python
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
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k cmd_push -v`
Expected: PASS (8 tests).

- [ ] **Step 9: Write the failing test for the `main()` CLI wrapper**

Append to `tests/test_gitlab_ci.py`:

```python
def test_main_push_prints_one_json_line_and_exits_0(tmp_path, monkeypatch, capsys):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    _stub_mr_api(monkeypatch, existing=[{"iid": 3, "web_url": "https://x/3", "source_project_id": 90}])

    code = gitlab_ci.main(["push", "--target", "dev"])

    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["mr_iid"] == 3


def test_main_wraps_message_only_systemexit_as_10(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_push", lambda **kw: (_ for _ in ()).throw(
        SystemExit("error: boom")))
    code = gitlab_ci.main(["push"])
    assert code == 10


def test_main_passes_through_int_systemexit(monkeypatch):
    monkeypatch.setattr(gitlab_ci, "cmd_push", lambda **kw: (_ for _ in ()).throw(SystemExit(4)))
    assert gitlab_ci.main(["push"]) == 4
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k test_main -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'main'`.

- [ ] **Step 11: Implement `main()`**

Add at the end of `scripts/gitlab_ci.py`:

```python
def _build_parser() -> "argparse.ArgumentParser":
    import argparse
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
        print(str(e.code), file=__import__("sys").stderr)
        return 10
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
```

Move `import argparse` and `import sys` to the top of the file's import
block (with the other stdlib imports) instead of the inline/local imports
shown above — those are written inline here only so this step's diff is
self-contained; the final file must import both at module level, matching
every other stdlib import in this file.

- [ ] **Step 12: Run all Task 2 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (all tests from Tasks 1–2).

- [ ] **Step 13: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): push command + MR reuse/create + CLI entrypoint

git-only helpers (current_branch, has_tracked_changes, rebase_onto)
plus cmd_push: refuses a dirty tracked tree or a protected/target
branch, rebases onto upstream/<target> (aborting cleanly on conflict,
exit 4), force-with-lease pushes to origin, and reuses an open MR or
creates one with no auto-merge flags. main() wraps every command's
message-only SystemExit as exit 10, passing int SystemExits through."
```

---

### Task 3: `wait` command

**Files:**
- Modify: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `cmd_wait(mr_iid, sha, since=None, timeout_minutes=120,
  sleep_fn=time.sleep, now_fn=time.time) -> dict` and a `wait` subparser on
  `main()`. `sleep_fn`/`now_fn` are injection points for tests — production
  callers never pass them.
- Consumes: `load_project_config`, `resolve_gitlab_token`,
  `git_remote_project_path`, `gitlab_project_id`, `api_request` (Tasks 1–2);
  `events_dir` (Task 1).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gitlab_ci.py`:

```python
def _wait_env(monkeypatch, gets):
    """`gets` maps exact URL -> response dict; api_request(GET, url) looks it
    up. Any POST/other method is an error — wait never writes."""
    def fake_api_request(token, method, url, data=None, **kw):
        assert method == "GET"
        return gets[url]

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})


def _write_event(events_root, project_id, pipeline_id, received_ns, iid, sha, status):
    d = events_root / str(project_id) / str(pipeline_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{received_ns}.json").write_text(json.dumps({
        "object_kind": "pipeline",
        "object_attributes": {"id": pipeline_id, "sha": sha, "status": status},
        "merge_request": {"iid": iid, "source_project_id": 90},
        "project": {"id": project_id},
    }), encoding="utf-8")


def test_cmd_wait_initial_get_counting_status(monkeypatch):
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {
        "head_pipeline": {"id": 55, "project_id": 21, "sha": "abc",
                           "status": "success", "web_url": "https://x/p/55",
                           "finished_at": "2026-09-11T10:00:00.000Z"}}})

    result = gitlab_ci.cmd_wait(mr_iid=7, sha="abc")
    assert result == {"pipeline_id": 55, "project_id": 21,
                       "status": "success", "web_url": "https://x/p/55"}


def test_cmd_wait_since_rejects_stale_final_status(monkeypatch):
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    since = 2_000_000_000_000_000_000  # far in the future
    _wait_env(monkeypatch, {mr_url: {
        "head_pipeline": {"id": 55, "project_id": 21, "sha": "abc",
                           "status": "success", "web_url": "https://x/p/55",
                           "finished_at": "2026-09-11T10:00:00.000Z"}}})

    calls = {"sleep": 0}

    def sleep_and_stop(_s):
        calls["sleep"] += 1
        raise SystemExit(3)  # abort the loop after one pass, like a real timeout would

    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc", since=since, sleep_fn=sleep_and_stop, now_fn=lambda: 0)
    except SystemExit:
        pass
    # since is stale relative to finished_at -> falls through to event scanning,
    # which sleeps once before this test's injected sleep_fn aborts the loop
    assert calls["sleep"] == 1


def test_cmd_wait_scans_events_dir_for_final_status(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    pipeline_url = "https://gitlab.vdx.vn/api/v4/projects/21/pipelines/55"
    _wait_env(monkeypatch, {
        mr_url: {"head_pipeline": {"id": 55, "project_id": 21, "sha": "old",
                                    "status": "success", "finished_at": None}},
        pipeline_url: {"id": 55, "status": "failed", "web_url": "https://x/p/55",
                        "finished_at": "2026-09-11T10:00:00.000Z"},
    })
    _write_event(tmp_path, project_id=21, pipeline_id=55, received_ns=100,
                 iid=7, sha="abc", status="failed")

    result = gitlab_ci.cmd_wait(mr_iid=7, sha="abc", sleep_fn=lambda s: None,
                                 now_fn=lambda: 0)
    assert result == {"pipeline_id": 55, "project_id": 21,
                       "status": "failed", "web_url": "https://x/p/55"}


def test_cmd_wait_ignores_events_for_other_iid_sha_or_before_since(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {"head_pipeline": {"sha": "old", "status": "success"}}})
    _write_event(tmp_path, 21, 1, received_ns=50, iid=99, sha="abc", status="success")   # wrong iid
    _write_event(tmp_path, 21, 2, received_ns=50, iid=7, sha="zzz", status="success")    # wrong sha
    _write_event(tmp_path, 21, 3, received_ns=5, iid=7, sha="abc", status="success")     # before since

    calls = {"n": 0}

    def sleep_and_stop(_s):
        calls["n"] += 1
        raise SystemExit(3)  # abort the test after one scan pass, like a timeout would

    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc", since=10, sleep_fn=sleep_and_stop, now_fn=lambda: 0)
    except SystemExit:
        pass
    assert calls["n"] == 1  # none of the three events matched -> kept scanning


def test_cmd_wait_no_pipeline_after_10_minutes_exits_3(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {"head_pipeline": {"sha": "old", "status": "success"}}})

    clock = {"t": 0.0}
    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc",
                            sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s),
                            now_fn=lambda: clock["t"])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "no_pipeline"


def test_cmd_wait_timeout_flag_exits_3(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {"head_pipeline": {"sha": "abc", "status": "running"}}})

    clock = {"t": 0.0}
    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc", timeout_minutes=1,
                            sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s),
                            now_fn=lambda: clock["t"])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k cmd_wait -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'cmd_wait'`.

- [ ] **Step 3: Implement `cmd_wait`**

Add `from datetime import datetime` to the top-level imports (with the other
stdlib imports).

Add to `scripts/gitlab_ci.py`, after `create_mr`/`push_ref` (from Task 2):

```python
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
```

Add a `wait` subparser inside `_build_parser()` (Task 2), after the `push`
subparser:

```python
    wait = sub.add_parser("wait")
    wait.add_argument("--mr", type=int, required=True, dest="mr_iid")
    wait.add_argument("--sha", required=True)
    wait.add_argument("--since", type=int)
    wait.add_argument("--timeout", type=int, default=120)
```

And a branch in `main()`'s dispatch, after the `push` branch:

```python
        elif args.cmd == "wait":
            result = cmd_wait(mr_iid=args.mr_iid, sha=args.sha, since=args.since,
                               timeout_minutes=args.timeout)
```

- [ ] **Step 4: Run all Task 3 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k cmd_wait -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full test suite**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (all tests from Tasks 1–3).

- [ ] **Step 6: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): wait command (webhook-event-driven, no polling)

cmd_wait does one initial GET of the MR's head_pipeline, then scans
docker/events/ every 5s for a matching pipeline webhook delivery,
confirming any final status with one GET of that pipeline before
trusting it (out-of-order delivery, stale status after a retry-job).
Exits 0/1/2 by pipeline status, 3 with a reason on no_pipeline/timeout."
```

---

### Task 4: `fetch-logs` command

**Files:**
- Modify: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `api_request_raw(token, url) -> bytes`; `_clean_trace(raw: bytes)
  -> str`; `_safe_extract(zip_bytes: bytes, dest: Path) -> None`;
  `cmd_fetch_logs(project_id, pipeline_id, out_dir) -> dict`; a `fetch-logs`
  subparser on `main()`.
- Consumes: `load_project_config`, `resolve_gitlab_token`, `api_request`
  (Task 1); `USER_AGENT` (Task 1).

- [ ] **Step 1: Write the failing tests**

Add `import io` and `import zipfile` to the top of `tests/test_gitlab_ci.py`.

Append to `tests/test_gitlab_ci.py`:

```python
def _fetch_logs_env(monkeypatch, jobs, raw=None):
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, data=None, **kw: jobs)
    monkeypatch.setattr(gitlab_ci, "api_request_raw", raw or (lambda token, url: b"trace\n"))
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})


def test_api_request_raw_sends_auth_and_user_agent(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert req.headers["Authorization"] == "Bearer TOK"
        assert req.headers["User-agent"] == gitlab_ci.USER_AGENT
        return io.BytesIO(b"raw-bytes")

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    assert gitlab_ci.api_request_raw("TOK", "https://x/y") == b"raw-bytes"


def test_clean_trace_strips_ansi_and_timestamp_prefix():
    raw = (b"2026-09-11T10:00:00.123456Z 00O \x1b[32mok\x1b[0m\n"
           b"2026-09-11T10:00:01.000000Z 00O+ next line\n")
    assert gitlab_ci._clean_trace(raw) == "ok\nnext line\n"


def test_cmd_fetch_logs_skips_allow_failure_and_non_failed(monkeypatch, tmp_path):
    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "ruff", "stage": "quality", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure", "artifacts": []},
        {"id": 2, "name": "security-scan", "stage": "test", "status": "failed",
         "allow_failure": True, "failure_reason": "script_failure", "artifacts": []},
        {"id": 3, "name": "pytest", "stage": "test", "status": "success",
         "allow_failure": False, "failure_reason": None, "artifacts": []},
    ])

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))

    assert [j["job"] for j in result["jobs"]] == ["ruff"]
    assert (tmp_path / "ruff.log").read_text(encoding="utf-8") == "trace\n"


def test_cmd_fetch_logs_unzips_archive_artifact(monkeypatch, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("parallel-odoo-test.log", "FAILED some::test\n")
    zip_bytes = buf.getvalue()

    def fake_raw(token, url):
        return zip_bytes if url.endswith("/artifacts") else b"trace\n"

    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "parallel-odoo-pytest", "stage": "test", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure",
         "artifacts": [{"file_type": "archive", "filename": "artifacts.zip"}]},
    ], raw=fake_raw)

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))

    assert result["jobs"][0]["artifacts"] == str(tmp_path / "parallel-odoo-pytest")
    assert (tmp_path / "parallel-odoo-pytest" / "parallel-odoo-test.log").read_text(
        encoding="utf-8") == "FAILED some::test\n"


def test_cmd_fetch_logs_no_archive_artifacts_is_null(monkeypatch, tmp_path):
    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "ruff", "stage": "quality", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure", "artifacts": []},
    ])

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))
    assert result["jobs"][0]["artifacts"] is None


def test_safe_extract_rejects_zip_slip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")

    try:
        gitlab_ci._safe_extract(buf.getvalue(), tmp_path / "job-name")
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert not (tmp_path.parent / "evil.txt").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "fetch_logs or clean_trace or safe_extract or api_request_raw" -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 3: Implement `api_request_raw`, `_clean_trace`, `_safe_extract`, `cmd_fetch_logs`**

Add `import io` and `import zipfile` to the top-level imports of
`scripts/gitlab_ci.py`.

Add after `cmd_wait`:

```python
def api_request_raw(token: str, url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
                                                "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error: GitLab API GET {url} returned {e.code}")
    except (urllib.error.URLError, TimeoutError) as e:
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
```

Add a `fetch-logs` subparser inside `_build_parser()`, after `wait`:

```python
    fetch_logs = sub.add_parser("fetch-logs")
    fetch_logs.add_argument("--project", type=int, required=True, dest="project_id")
    fetch_logs.add_argument("--pipeline", type=int, required=True, dest="pipeline_id")
    fetch_logs.add_argument("--out", required=True, dest="out_dir")
```

And a branch in `main()`'s dispatch, after `wait`:

```python
        elif args.cmd == "fetch-logs":
            result = cmd_fetch_logs(project_id=args.project_id, pipeline_id=args.pipeline_id,
                                     out_dir=args.out_dir)
```

- [ ] **Step 4: Run all Task 4 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "fetch_logs or clean_trace or safe_extract or api_request_raw" -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the full test suite**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (all tests from Tasks 1–4).

- [ ] **Step 6: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): fetch-logs command

For each failed, non-allow_failure job: trace fetched and cleaned
(ANSI codes and the <timestamp>Z <NN><O|E>[+] prefix stripped), any
archive artifact unzipped with a zip-slip guard that rejects entries
resolving outside the destination directory."
```

---

### Task 5: `lint` command

**Files:**
- Modify: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `parse_ci_config_path(raw) -> (file, project_path, ref)`;
  `repo_file_raw(token, gitlab_url, project_id, ref, file_path) -> str`;
  `_yaml_scalar(text, key) -> str | None`; `rewrite_ruff_ignore(ruff_toml_text,
  ignore_linters) -> str`; `cmd_lint(target="dev") -> dict`; a `lint`
  subparser on `main()`.
- Consumes: `load_project_config`, `resolve_gitlab_token`,
  `git_remote_project_path`, `gitlab_project_id`, `api_request`,
  `api_request_raw` (Tasks 1, 2, 4).

**Known open question — flag, don't fabricate:** the spec requires the local
`ruff.toml` rewrite to be "identical to `get_ignore_file_command_ruff`
output" (`scripts/utils.sh` in the `infra/cicd-pipeline-template` GitLab
project, not in this repo, not fetched for this plan). `rewrite_ruff_ignore`
below is a best-effort implementation (comma-separated `IGNORE_LINTERS` →
one `"<addon>/**"` glob per entry, replacing the `extend-exclude` line) —
**Step 3 below includes fetching and reading the real `scripts/utils.sh`
during implementation** to confirm or correct it before this task is
considered done; if the real transform differs, only `rewrite_ruff_ignore`
and its test change.

- [ ] **Step 1: Write the failing tests for parsing helpers**

Append to `tests/test_gitlab_ci.py`:

```python
def test_parse_ci_config_path():
    assert gitlab_ci.parse_ci_config_path(
        "pipelines/sun-sca.yml@infra/cicd-pipeline-template:sca") == \
        ("pipelines/sun-sca.yml", "infra/cicd-pipeline-template", "sca")


def test_parse_ci_config_path_malformed_exits():
    try:
        gitlab_ci.parse_ci_config_path("not-a-valid-path")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_yaml_scalar_extracts_quoted_value():
    text = 'variables:\n  ENABLE_RUFF: "true"\n  IGNORE_LINTERS: "mod_a,mod_b"\n'
    assert gitlab_ci._yaml_scalar(text, "ENABLE_RUFF") == "true"
    assert gitlab_ci._yaml_scalar(text, "IGNORE_LINTERS") == "mod_a,mod_b"


def test_yaml_scalar_missing_key_returns_none():
    assert gitlab_ci._yaml_scalar("variables:\n  X: 1\n", "ENABLE_RUFF") is None


def test_rewrite_ruff_ignore_replaces_extend_exclude_line():
    toml = 'line-length = 180\nextend-exclude = ["old/**"]\ntarget-version = "py310"\n'
    rewritten = gitlab_ci.rewrite_ruff_ignore(toml, "mod_a,mod_b")
    assert 'extend-exclude = ["mod_a/**", "mod_b/**"]' in rewritten
    assert 'line-length = 180' in rewritten
    assert 'target-version = "py310"' in rewritten
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "ci_config_path or yaml_scalar or rewrite_ruff" -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 3: Confirm the ruff-ignore rewrite against the real CI template, then implement**

Before writing `rewrite_ruff_ignore`, fetch the real transform for
comparison:

```bash
cd /home/xmars/dev/vdx-vn/sca/addons
git fetch upstream sca 2>/dev/null || true
curl -s --header "PRIVATE-TOKEN: $(git config --get http.https://gitlab.vdx.vn/.extraheader 2>/dev/null || echo)" \
  "https://gitlab.vdx.vn/api/v4/projects/infra%2Fcicd-pipeline-template/repository/files/scripts%2Futils.sh/raw?ref=sca" \
  | grep -A 15 "get_ignore_file_command_ruff"
```

(If that curl needs real auth, use `gitlab_ci.resolve_gitlab_token` and
`repo_file_raw` interactively once they exist — chicken-and-egg only for
this one manual check, not for the implementation itself.) Compare the shell
function's actual `sed`/`awk` transform against `rewrite_ruff_ignore` below;
adjust the implementation and Step 1's test to match before proceeding.
**Do not skip this check** — a mismatch here means `lint` silently
diverges from what CI's `ruff` job actually excludes, producing findings
CI would never have flagged (false escalations under rule 3) or missing
ones CI would (false-green local preflight).

Add to `scripts/gitlab_ci.py`, after `cmd_fetch_logs`:

```python
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
    new_text, count = re.subn(r"^extend-exclude.*$", replacement, ruff_toml_text,
                               count=1, flags=re.MULTILINE)
    if count == 0:
        return ruff_toml_text.rstrip("\n") + "\n" + replacement + "\n"
    return new_text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "ci_config_path or yaml_scalar or rewrite_ruff" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing tests for `cmd_lint`**

Append to `tests/test_gitlab_ci.py`:

```python
def _lint_env(monkeypatch, ci_yaml, dockerfile="FROM x\nRUN pip install ruff==0.15.20\n",
              ruff_toml='extend-exclude = ["old/**"]\n', uvx_stdout="[]", changed_files=()):
    files = {
        "pipelines/sun-sca.yml": ci_yaml,
        "config/docker/Dockerfile.cicd-runner": dockerfile,
        "config/linters/ruff/ruff.toml": ruff_toml,
    }

    def fake_api_request(token, method, url, data=None, **kw):
        return {"id": 90, "ci_config_path": "pipelines/sun-sca.yml@infra/cicd-pipeline-template:sca"}

    def fake_raw(token, url):
        for name, content in files.items():
            if urllib.parse.quote(name, safe="") in url:
                return content.encode("utf-8")
        raise AssertionError(f"unexpected raw URL {url}")

    def fake_run(args, cwd=None, capture_output=None, text=None, check=None, **kw):
        if args[0] == "uvx":
            return subprocess.CompletedProcess(args, 0, stdout=uvx_stdout, stderr="")
        if args[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(args, 0, stdout="\n".join(changed_files), stderr="")
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "api_request_raw", fake_raw)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 90)
    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn",
                                  "addons_dir": "/repo/addons"})


def test_cmd_lint_disabled_returns_skipped(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "false"\n')
    assert gitlab_ci.cmd_lint(target="dev") == {"skipped": True}


def test_cmd_lint_unparsable_version_exits_10(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n', dockerfile="FROM x\n")
    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_cmd_lint_no_findings(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n  IGNORE_LINTERS: ""\n',
              uvx_stdout="[]")
    result = gitlab_ci.cmd_lint(target="dev")
    assert result == {"ruff_version": "0.15.20", "findings": []}


def test_cmd_lint_findings_flag_in_branch_and_exit_1(monkeypatch, capsys):
    findings_json = json.dumps([
        {"filename": "/repo/addons/module_a/models/x.py", "location": {"row": 12},
         "code": "F401", "message": "unused import"},
        {"filename": "/repo/addons/module_b/models/y.py", "location": {"row": 3},
         "code": "E501", "message": "line too long"},
    ])
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n',
              uvx_stdout=findings_json, changed_files=["addons/module_a/models/x.py"])

    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 1
    printed = json.loads(capsys.readouterr().out)
    by_file = {f["file"]: f["in_branch"] for f in printed["findings"]}
    assert by_file["/repo/addons/module_a/models/x.py"] is True
    assert by_file["/repo/addons/module_b/models/y.py"] is False
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k cmd_lint -v`
Expected: FAIL — `AttributeError: module 'gitlab_ci' has no attribute 'cmd_lint'`.

- [ ] **Step 7: Implement `cmd_lint`**

Add `import tempfile` to the top-level imports of `scripts/gitlab_ci.py`.

Add after `rewrite_ruff_ignore`:

```python
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
        result = subprocess.run(
            ["uvx", f"ruff@{ruff_version}", "check", "--config", str(tmp_config),
             "--output-format", "json", addons_dir],
            capture_output=True, text=True)
    finally:
        tmp_config.unlink(missing_ok=True)

    raw_findings = json.loads(result.stdout or "[]")
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
```

Add a `lint` subparser inside `_build_parser()`, after `fetch-logs`:

```python
    lint = sub.add_parser("lint")
    lint.add_argument("--target", default="dev")
```

And a branch in `main()`'s dispatch, after `fetch-logs`:

```python
        elif args.cmd == "lint":
            result = cmd_lint(target=args.target)
```

- [ ] **Step 8: Run all Task 5 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k cmd_lint -v`
Expected: PASS (4 tests).

- [ ] **Step 9: Run the full test suite**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (all tests from Tasks 1–5).

- [ ] **Step 10: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): lint command (local ruff mirroring CI)

Parses the upstream project's ci_config_path to read IGNORE_LINTERS/
ENABLE_RUFF, the pinned ruff version, and ruff.toml from the CI
template project; rewrites extend-exclude (verified against
scripts/utils.sh's get_ignore_file_command_ruff); runs uvx ruff@<version>
locally and flags each finding's in_branch status against the diff."
```

---

### Task 6: `retry-job`, `notify`, `clean` commands

**Files:**
- Modify: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `cmd_retry_job(project_id, job_id) -> dict`;
  `cmd_notify(text) -> dict`; `cmd_clean(mr_iid) -> dict`; `retry-job`,
  `notify`, `clean` subparsers on `main()`.
- Consumes: `load_project_config`, `resolve_gitlab_token`, `api_request`,
  `USER_AGENT`, `events_dir` (Task 1).

- [ ] **Step 1: Write the failing tests**

Add `import shutil` to the top of `scripts/gitlab_ci.py`'s import block (not
needed in the test file).

Append to `tests/test_gitlab_ci.py`:

```python
def test_cmd_retry_job(monkeypatch):
    def fake_api_request(token, method, url, data=None, **kw):
        assert method == "POST"
        assert url == "https://gitlab.vdx.vn/api/v4/projects/21/jobs/999/retry"
        return {"id": 1000, "pipeline": {"id": 56}}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})

    result = gitlab_ci.cmd_retry_job(project_id=21, job_id=999)
    assert result["job_id"] == 1000
    assert result["pipeline_id"] == 56
    assert isinstance(result["since"], int)


def test_cmd_notify_sends_and_reports_sent(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data)
        seen["headers"] = dict(req.headers)
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn",
                                  "telegram_channel": "-100", "telegram_token": "BOTTOK"})

    result = gitlab_ci.cmd_notify(text="MR !3 green")
    assert result == {"telegram": "sent"}
    assert seen["url"] == "https://api.telegram.org/botBOTTOK/sendMessage"
    assert seen["body"] == {"chat_id": "-100", "text": "MR !3 green"}
    assert seen["headers"]["User-agent"] == gitlab_ci.USER_AGENT


def test_cmd_notify_failure_reports_reason_exit_0(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn",
                                  "telegram_channel": "-100", "telegram_token": "BOTTOK"})

    result = gitlab_ci.cmd_notify(text="x")
    assert result["telegram"].startswith("failed:")
    assert "BOTTOK" not in json.dumps(result)  # token never printed


def test_cmd_notify_missing_config_reports_failed(monkeypatch):
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    result = gitlab_ci.cmd_notify(text="x")
    assert result["telegram"].startswith("failed:")


def test_cmd_clean_removes_only_matching_pipeline_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    d1 = tmp_path / "21" / "55"
    d1.mkdir(parents=True)
    (d1 / "100.json").write_text(json.dumps({"merge_request": {"iid": 7}}), encoding="utf-8")
    d2 = tmp_path / "21" / "56"
    d2.mkdir(parents=True)
    (d2 / "101.json").write_text(json.dumps({"merge_request": {"iid": 8}}), encoding="utf-8")

    result = gitlab_ci.cmd_clean(mr_iid=7)

    assert result == {"removed": [55]}
    assert not d1.exists()
    assert d2.exists()


def test_cmd_clean_no_events_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "nope")
    assert gitlab_ci.cmd_clean(mr_iid=7) == {"removed": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "retry_job or notify or cmd_clean" -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 3: Implement `cmd_retry_job`, `cmd_notify`, `cmd_clean`**

Add after `cmd_lint`:

```python
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
```

Add three subparsers inside `_build_parser()`, after `lint`:

```python
    retry_job = sub.add_parser("retry-job")
    retry_job.add_argument("--project", type=int, required=True, dest="project_id")
    retry_job.add_argument("--job", type=int, required=True, dest="job_id")

    notify = sub.add_parser("notify")
    notify.add_argument("--text", required=True)

    clean = sub.add_parser("clean")
    clean.add_argument("--mr", type=int, required=True, dest="mr_iid")
```

And three branches in `main()`'s dispatch, after `lint`:

```python
        elif args.cmd == "retry-job":
            result = cmd_retry_job(project_id=args.project_id, job_id=args.job_id)
        elif args.cmd == "notify":
            result = cmd_notify(text=args.text)
        elif args.cmd == "clean":
            result = cmd_clean(mr_iid=args.mr_iid)
```

- [ ] **Step 4: Run all Task 6 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "retry_job or notify or cmd_clean" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full test suite**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (all tests from Tasks 1–6).

- [ ] **Step 6: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): retry-job, notify, clean commands

retry-job POSTs the GitLab retry endpoint and returns a fresh since
for wait's next call; notify sends a Telegram message and always
exits 0, reporting failure in the JSON instead (token never printed);
clean deletes only the events/<project>/<pipeline>/ directories whose
stored events carry the given MR iid."
```

---

### Task 7: `setup` and `check-setup` commands

**Files:**
- Modify: `skills/odoo-deploy/scripts/gitlab_ci.py`
- Test: `skills/odoo-deploy/tests/test_gitlab_ci.py`

**Interfaces:**
- Produces: `cmd_setup() -> dict`; `cmd_check_setup() -> dict`; `setup`,
  `check-setup` subparsers on `main()`.
- Consumes: everything from Tasks 1–6 (`load_project_config`,
  `resolve_gitlab_token`, `git_remote_project_path`, `gitlab_project_id`,
  `api_request`, `parse_remote_url`, `events_dir`, `skill_dir`,
  `TELEGRAM_API_BASE`, `USER_AGENT`).

**Note on check `d`:** `docker compose ps --format json` is treated as
JSON-Lines (one JSON object per `docker compose` line), matching current
Docker Compose v2 — confirm against the actual installed `docker compose
version` during implementation; if it instead emits one JSON array, adjust
`_check_d` and its test only.

- [ ] **Step 1: Write the failing tests for the env-file helpers**

Add `import secrets` to the top of `scripts/gitlab_ci.py`'s import block.

Append to `tests/test_gitlab_ci.py`:

```python
def test_read_env_file_parses_key_value_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("TUNNEL_TOKEN=abc\n# comment\nHOOK_HOSTNAME=x.vdx.vn\n\n", encoding="utf-8")
    assert gitlab_ci._read_env_file(p) == {"TUNNEL_TOKEN": "abc", "HOOK_HOSTNAME": "x.vdx.vn"}


def test_read_env_file_missing_returns_empty(tmp_path):
    assert gitlab_ci._read_env_file(tmp_path / "nope") == {}


def test_write_env_file_sets_permissions_600(tmp_path):
    p = tmp_path / ".env"
    gitlab_ci._write_env_file(p, {"A": "1", "B": "2"})
    assert p.read_text(encoding="utf-8") == "A=1\nB=2\n"
    assert (p.stat().st_mode & 0o777) == 0o600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k env_file -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 3: Implement `_read_env_file`/`_write_env_file`**

Add after `cmd_clean`:

```python
ENV_REQUIRED = ("TUNNEL_TOKEN", "HOOK_HOSTNAME")
ENV_AUTO = ("WEBHOOK_SECRET", "FORK_PROJECT_ID", "LISTENER_UID", "LISTENER_GID")
ENV_ALL_KEYS = ENV_REQUIRED + ENV_AUTO


def _read_env_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _write_env_file(path: Path, env: dict) -> None:
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    path.chmod(0o600)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k env_file -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing tests for the eight check functions**

Append to `tests/test_gitlab_ci.py`:

```python
def _checks_env(monkeypatch, tmp_path, git_root="/repo", gitlab_url="https://gitlab.vdx.vn",
                 remotes=None, telegram=None):
    remotes = remotes if remotes is not None else {
        "origin": "https://gitlab.vdx.vn/truong/sca.git",
        "upstream": "https://gitlab.vdx.vn/sungroup/sca",
    }
    cfg = {"git_root": git_root, "gitlab_url": gitlab_url}
    if telegram:
        cfg.update(telegram)

    def fake_git_remote_url(remote, root):
        return remotes.get(remote)

    monkeypatch.setattr(gitlab_ci, "load_project_config", lambda: cfg)
    monkeypatch.setattr(gitlab_ci, "_git_remote_url", fake_git_remote_url)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "docker" / "events")
    return cfg


def test_check_a_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ok, _ = gitlab_ci._check_a()
    assert ok is True


def test_check_a_fails_without_upstream_remote(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path, remotes={"origin": "https://gitlab.vdx.vn/truong/sca.git"})
    ok, detail = gitlab_ci._check_a()
    assert ok is False and "upstream" in detail


def test_check_a_fails_on_host_mismatch(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path, remotes={
        "origin": "https://gitlab.vdx.vn/truong/sca.git",
        "upstream": "https://gitlab.other.example/sungroup/sca",
    })
    ok, detail = gitlab_ci._check_a()
    assert ok is False and "host" in detail


def test_check_b_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, **kw: {"id": 1})
    ok, _ = gitlab_ci._check_b()
    assert ok is True


def test_check_b_fails_on_auth_error(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)

    def boom(token, method, url, **kw):
        raise SystemExit("error: GitLab API GET .../user returned 401: ...")

    monkeypatch.setattr(gitlab_ci, "api_request", boom)
    ok, detail = gitlab_ci._check_b()
    assert ok is False and "401" in detail


def test_check_c_reports_missing_keys(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"TUNNEL_TOKEN": "t"})
    ok, detail = gitlab_ci._check_c()
    assert ok is False
    assert "HOOK_HOSTNAME" in detail


def test_check_c_ok_when_all_keys_present(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env",
                               {k: "x" for k in gitlab_ci.ENV_ALL_KEYS})
    ok, _ = gitlab_ci._check_c()
    assert ok is True


def test_check_d_reports_missing_services(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)

    def fake_run(args, **kw):
        assert args[:2] == ["docker", "compose"]
        out = '{"Service": "cloudflared", "State": "running"}\n'
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    ok, detail = gitlab_ci._check_d()
    assert ok is False and "listener" in detail


def test_check_d_ok_when_both_running(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)

    def fake_run(args, **kw):
        out = ('{"Service": "cloudflared", "State": "running"}\n'
               '{"Service": "listener", "State": "running"}\n')
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    ok, _ = gitlab_ci._check_d()
    assert ok is True


def test_check_e_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, **kw: [
        {"url": "https://x.vdx.vn/hook", "pipeline_events": True, "alert_status": "executable"}])
    ok, _ = gitlab_ci._check_e()
    assert ok is True


def test_check_e_fails_wrong_alert_status(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, **kw: [
        {"url": "https://x.vdx.vn/hook", "pipeline_events": True, "alert_status": "disabled"}])
    ok, detail = gitlab_ci._check_e()
    assert ok is False and "alert_status" in detail


def test_check_f_ok_when_uvx_on_path(monkeypatch):
    monkeypatch.setattr(gitlab_ci.shutil, "which", lambda name: "/usr/bin/uvx")
    assert gitlab_ci._check_f() == (True, "ok")


def test_check_f_fails_when_uvx_missing(monkeypatch):
    monkeypatch.setattr(gitlab_ci.shutil, "which", lambda name: None)
    ok, detail = gitlab_ci._check_f()
    assert ok is False and "uvx" in detail


def test_check_g_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path, telegram={"telegram_channel": "-1", "telegram_token": "BOT"})

    def fake_urlopen(req, timeout=None):
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    ok, _ = gitlab_ci._check_g()
    assert ok is True


def test_check_g_fails_missing_config(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ok, detail = gitlab_ci._check_g()
    assert ok is False and "telegram" in detail


def test_check_h_detects_last_delivery_change(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ev_dir = tmp_path / "docker" / "events"
    ev_dir.mkdir(parents=True)
    (tmp_path / "docker").mkdir(exist_ok=True)
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    (ev_dir / ".last_delivery").write_text("before", encoding="utf-8")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)

    calls = {"n": 0}

    def fake_api_request(token, method, url, data=None, **kw):
        if method == "GET":
            return [{"id": 9, "url": "https://x.vdx.vn/hook"}]
        calls["n"] += 1
        (ev_dir / ".last_delivery").write_text("after", encoding="utf-8")
        return {}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    ok, _ = gitlab_ci._check_h(sleep_fn=lambda s: None, now_fn=lambda: 0)
    assert ok is True
    assert calls["n"] == 1


def test_check_h_times_out_without_delivery(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ev_dir = tmp_path / "docker" / "events"
    ev_dir.mkdir(parents=True)
    (tmp_path / "docker").mkdir(exist_ok=True)
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, data=None, **kw:
                         [{"id": 9, "url": "https://x.vdx.vn/hook"}] if method == "GET" else {})

    clock = {"t": 0.0}
    ok, detail = gitlab_ci._check_h(
        sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s), now_fn=lambda: clock["t"])
    assert ok is False and "15s" in detail
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "check_a or check_b or check_c or check_d or check_e or check_f or check_g or check_h" -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 7: Implement the eight check functions**

Add after `_write_env_file`:

```python
def _git_remote_url(remote: str, git_root: str) -> str | None:
    result = subprocess.run(["git", "remote", "get-url", remote], cwd=git_root,
                             capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _check_a() -> tuple[bool, str]:
    try:
        cfg = load_project_config()
    except SystemExit as e:
        return False, str(e.code)
    git_root, gitlab_url = cfg["git_root"], cfg["gitlab_url"]
    origin_url = _git_remote_url("origin", git_root)
    if origin_url is None:
        return False, f"no 'origin' git remote in {git_root}"
    upstream_url = _git_remote_url("upstream", git_root)
    if upstream_url is None:
        return False, f"no 'upstream' git remote in {git_root}"
    upstream_host, _ = parse_remote_url(upstream_url)
    gitlab_host = urllib.parse.urlparse(gitlab_url).netloc
    if upstream_host != gitlab_host:
        return False, f"upstream remote host {upstream_host!r} != gitlab_url host {gitlab_host!r}"
    return True, "ok"


def _check_b() -> tuple[bool, str]:
    try:
        cfg = load_project_config()
        token = resolve_gitlab_token(urllib.parse.urlparse(cfg["gitlab_url"]).netloc)
        api_request(token, "GET", f"{cfg['gitlab_url']}/api/v4/user")
    except SystemExit as e:
        return False, str(e.code)
    return True, "ok"


def _check_c() -> tuple[bool, str]:
    env = _read_env_file(skill_dir() / "docker" / ".env")
    missing = [k for k in ENV_ALL_KEYS if not env.get(k)]
    if missing:
        return False, f"docker/.env missing {missing}"
    return True, "ok"


def _check_d() -> tuple[bool, str]:
    compose_path = skill_dir() / "docker" / "compose.yml"
    result = subprocess.run(["docker", "compose", "-f", str(compose_path), "ps", "--format", "json"],
                             capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr.strip()
    running = set()
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        service = json.loads(line)
        if service.get("State") == "running":
            running.add(service.get("Service"))
    missing = {"cloudflared", "listener"} - running
    if missing:
        return False, f"not running: {sorted(missing)}"
    return True, "ok"


def _check_e() -> tuple[bool, str]:
    try:
        cfg = load_project_config()
        gitlab_url = cfg["gitlab_url"]
        token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
        env = _read_env_file(skill_dir() / "docker" / ".env")
        hostname = env.get("HOOK_HOSTNAME")
        if not hostname:
            return False, "HOOK_HOSTNAME not set in docker/.env"
        upstream_id = gitlab_project_id(token, gitlab_url,
                                         git_remote_project_path("upstream", cfg["git_root"]))
        hooks = api_request(token, "GET", f"{gitlab_url}/api/v4/projects/{upstream_id}/hooks")
    except SystemExit as e:
        return False, str(e.code)
    hook_url = f"https://{hostname}/hook"
    matching = [h for h in hooks if h.get("url") == hook_url]
    if len(matching) != 1:
        return False, f"expected exactly one hook at {hook_url}, found {len(matching)}"
    hook = matching[0]
    if not hook.get("pipeline_events"):
        return False, "hook exists but pipeline_events is not enabled"
    if hook.get("alert_status") != "executable":
        return False, f"hook alert_status is {hook.get('alert_status')!r}, not 'executable'"
    return True, "ok"


def _check_f() -> tuple[bool, str]:
    if shutil.which("uvx") is None:
        return False, "'uvx' not found on PATH"
    return True, "ok"


def _check_g() -> tuple[bool, str]:
    try:
        cfg = load_project_config()
    except SystemExit as e:
        return False, str(e.code)
    channel, token = cfg.get("telegram_channel"), cfg.get("telegram_token")
    if not channel or not token:
        return False, "telegram_channel/telegram_token missing from config/project.json"
    req = urllib.request.Request(f"{TELEGRAM_API_BASE}/bot{token}/getMe",
                                  headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return False, f"Telegram getMe failed: {e}"
    if not result.get("ok"):
        return False, f"Telegram getMe failed: {result.get('description', result)}"
    return True, "ok"


def _check_h(sleep_fn=time.sleep, now_fn=time.time) -> tuple[bool, str]:
    cfg = load_project_config()
    gitlab_url = cfg["gitlab_url"]
    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    upstream_id = gitlab_project_id(token, gitlab_url,
                                     git_remote_project_path("upstream", cfg["git_root"]))
    env = _read_env_file(skill_dir() / "docker" / ".env")
    hook_url = f"https://{env.get('HOOK_HOSTNAME')}/hook"
    hooks = api_request(token, "GET", f"{gitlab_url}/api/v4/projects/{upstream_id}/hooks")
    hook = next((h for h in hooks if h.get("url") == hook_url), None)
    if hook is None:
        return False, f"no hook at {hook_url} to test"

    marker_path = events_dir() / ".last_delivery"
    before = marker_path.read_text(encoding="utf-8") if marker_path.is_file() else None
    api_request(token, "POST", f"{gitlab_url}/api/v4/projects/{upstream_id}"
                                f"/hooks/{hook['id']}/test/pipeline_events")

    deadline = now_fn() + 15
    while now_fn() < deadline:
        after = marker_path.read_text(encoding="utf-8") if marker_path.is_file() else None
        if after is not None and after != before:
            return True, "ok"
        sleep_fn(1)
    return False, "no delivery observed within 15s"
```

- [ ] **Step 8: Run all Task 7 check tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "check_a or check_b or check_c or check_d or check_e or check_f or check_g or check_h" -v`
Expected: PASS (16 tests).

- [ ] **Step 9: Write the failing tests for `cmd_check_setup` and `cmd_setup`**

Append to `tests/test_gitlab_ci.py`:

```python
def _stub_all_checks(monkeypatch, ok=True):
    for check_id in "abcdefg":
        monkeypatch.setattr(gitlab_ci, f"_check_{check_id}", lambda: (ok, "ok" if ok else "bad"))
    monkeypatch.setattr(gitlab_ci, "_check_h", lambda **kw: (ok, "ok" if ok else "bad"))


def test_run_checks_skips_h_when_a_fails(monkeypatch):
    monkeypatch.setattr(gitlab_ci, "_check_a", lambda: (False, "no config"))
    for check_id in "bcdefg":
        monkeypatch.setattr(gitlab_ci, f"_check_{check_id}", lambda: (True, "ok"))
    called = {"h": False}
    monkeypatch.setattr(gitlab_ci, "_check_h", lambda **kw: called.__setitem__("h", True) or (True, "ok"))

    result = gitlab_ci._run_checks()

    assert result["ok"] is False
    assert called["h"] is False
    h_row = next(c for c in result["checks"] if c["id"] == "h")
    assert h_row["ok"] is False and "skipped" in h_row["detail"]


def test_run_checks_all_ok(monkeypatch):
    _stub_all_checks(monkeypatch, ok=True)
    result = gitlab_ci._run_checks()
    assert result["ok"] is True
    assert all(c["fix"] is None for c in result["checks"])


def test_cmd_check_setup_exits_11_on_failure(monkeypatch, capsys):
    _stub_all_checks(monkeypatch, ok=False)
    try:
        gitlab_ci.cmd_check_setup()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 11
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_cmd_check_setup_returns_ok(monkeypatch):
    _stub_all_checks(monkeypatch, ok=True)
    assert gitlab_ci.cmd_check_setup()["ok"] is True


def test_cmd_setup_missing_required_env_exits_11(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    (tmp_path / "docker").mkdir()
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    try:
        gitlab_ci.cmd_setup()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 11


def test_cmd_setup_fills_missing_keys_and_creates_hook(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "docker" / "events")
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    gitlab_ci._write_env_file(docker_dir / ".env",
                               {"TUNNEL_TOKEN": "tok", "HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path",
                         lambda remote, root: {"origin": "truong/sca", "upstream": "sungroup/sca"}[remote])
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id",
                         lambda token, url, path: {"truong/sca": 90, "sungroup/sca": 21}[path])
    monkeypatch.setattr(gitlab_ci.subprocess, "run",
                         lambda args, **kw: subprocess.CompletedProcess(args, 0, stdout="", stderr=""))
    api_calls = []

    def fake_api_request(token, method, url, data=None, **kw):
        api_calls.append((method, url, data))
        if method == "GET":
            return []
        return {"id": 9}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "_run_checks", lambda: {"ok": True, "checks": []})

    result = gitlab_ci.cmd_setup()

    env = gitlab_ci._read_env_file(docker_dir / ".env")
    assert set(gitlab_ci.ENV_AUTO) <= env.keys()
    assert result["hook"] == "created"
    assert result["hook_id"] == 9
    assert sorted(result["env_added"]) == sorted(gitlab_ci.ENV_AUTO)
    post_calls = [c for c in api_calls if c[0] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0][2]["pipeline_events"] is True
    assert post_calls[0][2]["push_events"] is False


def test_cmd_setup_updates_existing_hook(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "docker" / "events")
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    gitlab_ci._write_env_file(docker_dir / ".env", {k: "x" for k in gitlab_ci.ENV_ALL_KEYS})
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path",
                         lambda remote, root: {"origin": "truong/sca", "upstream": "sungroup/sca"}[remote])
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id",
                         lambda token, url, path: {"truong/sca": 90, "sungroup/sca": 21}[path])
    monkeypatch.setattr(gitlab_ci.subprocess, "run",
                         lambda args, **kw: subprocess.CompletedProcess(args, 0, stdout="", stderr=""))

    def fake_api_request(token, method, url, data=None, **kw):
        if method == "GET":
            return [{"id": 5, "url": "https://x/hook"}]
        return {}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "_run_checks", lambda: {"ok": True, "checks": []})

    result = gitlab_ci.cmd_setup()
    assert result["hook"] == "updated"
    assert result["hook_id"] == 5
    assert result["env_added"] == []
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "run_checks or cmd_check_setup or cmd_setup" -v`
Expected: FAIL — `AttributeError` for each missing function.

- [ ] **Step 11: Implement `_run_checks`, `cmd_check_setup`, `cmd_setup`**

Add after `_check_h`:

```python
CHECK_ORDER = ("a", "b", "c", "d", "e", "f", "g", "h")
CHECK_FUNCS = {"a": _check_a, "b": _check_b, "c": _check_c, "d": _check_d,
               "e": _check_e, "f": _check_f, "g": _check_g}
CHECK_FIXES = {
    "a": "run 'odoo setup' (odoo-cli) to write config/project.json, or add "
         "the missing origin/upstream git remote",
    "b": "add a ~/.gitlab [gitlab] entry or run 'git credential approve' with a working token",
    "c": "see README 'Cloudflare tunnel', then re-run 'gitlab_ci.py setup'",
    "d": "run 'docker compose -f skills/odoo-deploy/docker/compose.yml up -d'",
    "e": "run 'gitlab_ci.py setup' to (re)create the pipeline-events hook",
    "f": "install uv (https://docs.astral.sh/uv/) so 'uvx' is on PATH",
    "g": "run 'odoo setup --force --setup-telegram' (odoo-cli)",
    "h": "check the Cloudflare tunnel is running and HOOK_HOSTNAME resolves; "
         "see README 'Troubleshooting'",
}


def _run_checks() -> dict:
    checks = []
    prerequisites_ok = True
    for check_id in CHECK_ORDER:
        if check_id == "h":
            if not prerequisites_ok:
                checks.append({"id": "h", "ok": False, "detail": "skipped (a-e not ok)",
                               "fix": CHECK_FIXES["h"]})
                continue
            ok, detail = _check_h()
        else:
            ok, detail = CHECK_FUNCS[check_id]()
        checks.append({"id": check_id, "ok": ok, "detail": detail,
                       "fix": None if ok else CHECK_FIXES[check_id]})
        if check_id in ("a", "b", "c", "d", "e") and not ok:
            prerequisites_ok = False
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def cmd_check_setup() -> dict:
    result = _run_checks()
    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(11)
    return result


def cmd_setup() -> dict:
    cfg = load_project_config()
    git_root, gitlab_url = cfg["git_root"], cfg["gitlab_url"]
    env_path = skill_dir() / "docker" / ".env"
    env = _read_env_file(env_path)

    missing_required = [k for k in ENV_REQUIRED if not env.get(k)]
    if missing_required:
        print(json.dumps({"error": f"docker/.env missing {missing_required}; "
                                    f"see README 'Cloudflare tunnel'"}, ensure_ascii=False))
        raise SystemExit(11)

    token = resolve_gitlab_token(urllib.parse.urlparse(gitlab_url).netloc)
    added = []
    if not env.get("WEBHOOK_SECRET"):
        env["WEBHOOK_SECRET"] = secrets.token_urlsafe(32)
        added.append("WEBHOOK_SECRET")
    if not env.get("FORK_PROJECT_ID"):
        fork_path = git_remote_project_path("origin", git_root)
        env["FORK_PROJECT_ID"] = str(gitlab_project_id(token, gitlab_url, fork_path))
        added.append("FORK_PROJECT_ID")
    if not env.get("LISTENER_UID"):
        env["LISTENER_UID"] = str(os.getuid())
        added.append("LISTENER_UID")
    if not env.get("LISTENER_GID"):
        env["LISTENER_GID"] = str(os.getgid())
        added.append("LISTENER_GID")

    events_dir().mkdir(parents=True, exist_ok=True)
    _write_env_file(env_path, env)

    compose_path = skill_dir() / "docker" / "compose.yml"
    subprocess.run(["docker", "compose", "-f", str(compose_path), "up", "-d"],
                    check=True, capture_output=True, text=True)

    upstream_path = git_remote_project_path("upstream", git_root)
    upstream_id = gitlab_project_id(token, gitlab_url, upstream_path)
    hook_url = f"https://{env['HOOK_HOSTNAME']}/hook"
    hooks = api_request(token, "GET", f"{gitlab_url}/api/v4/projects/{upstream_id}/hooks")
    existing = next((h for h in hooks if h.get("url") == hook_url), None)
    hook_data = {"url": hook_url, "pipeline_events": True, "push_events": False,
                 "issues_events": False, "merge_requests_events": False,
                 "tag_push_events": False, "note_events": False, "job_events": False,
                 "deployment_events": False, "token": env["WEBHOOK_SECRET"],
                 "enable_ssl_verification": True}
    if existing is None:
        created = api_request(token, "POST", f"{gitlab_url}/api/v4/projects/{upstream_id}/hooks",
                               data=hook_data)
        hook_id, hook_state = created["id"], "created"
    else:
        api_request(token, "PUT",
                     f"{gitlab_url}/api/v4/projects/{upstream_id}/hooks/{existing['id']}",
                     data=hook_data)
        hook_id, hook_state = existing["id"], "updated"

    return {"hook_id": hook_id, "hook": hook_state, "env_added": added, "check": _run_checks()}
```

`CHECK_FUNCS` above intentionally omits `"h"` (handled by the explicit branch
in `_run_checks`, which also injects the skip row when `a`–`e` aren't all ok).

Add two subparsers inside `_build_parser()`, after `clean` (Task 6):

```python
    sub.add_parser("setup")
    sub.add_parser("check-setup")
```

And two branches in `main()`'s dispatch, after `clean`:

```python
        elif args.cmd == "setup":
            result = cmd_setup()
        elif args.cmd == "check-setup":
            result = cmd_check_setup()
```

- [ ] **Step 12: Run all Task 7 tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -k "run_checks or cmd_check_setup or cmd_setup" -v`
Expected: PASS (6 tests).

- [ ] **Step 13: Run the full test suite**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_gitlab_ci.py -v`
Expected: PASS (all tests from Tasks 1–7).

- [ ] **Step 14: Commit**

```bash
git add skills/odoo-deploy/scripts/gitlab_ci.py skills/odoo-deploy/tests/test_gitlab_ci.py
git commit -m "feat(odoo-deploy): setup and check-setup commands

setup fills missing docker/.env keys (chmod 600), brings up the
compose stack, and creates/updates the pipeline-events-only hook;
check-setup runs 8 independent checks (a-g gate h, which fires a real
test delivery and watches events/.last_delivery), exiting 11 with a
per-check fix on any failure."
```

---

### Task 8: `docker/listener.py` + `docker/compose.yml` + `docker/.env.example`

**Files:**
- Create: `skills/odoo-deploy/docker/listener.py`
- Create: `skills/odoo-deploy/docker/compose.yml`
- Create: `skills/odoo-deploy/docker/.env.example`
- Test: `skills/odoo-deploy/tests/test_listener.py`

**Interfaces:**
- Produces: `listener.Handler` (a `BaseHTTPRequestHandler` subclass) reading
  `WEBHOOK_SECRET`, `FORK_PROJECT_ID`, `EVENTS_DIR` from the process
  environment at import time — `docker/compose.yml` supplies the first two
  from `.env`, `EVENTS_DIR` defaults to `/events` (the container mount
  point) but is overridable, which is what makes the test importable outside
  the container.
- Consumes: nothing from `gitlab_ci.py` — `wait`/`clean` (Tasks 3, 6) only
  read the directory this handler writes into; no shared code.

- [ ] **Step 1: Write the failing tests**

Create `skills/odoo-deploy/tests/test_listener.py`:

```python
import http.client
import importlib
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docker"))


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "SECRET")
    monkeypatch.setenv("FORK_PROJECT_ID", "90")
    monkeypatch.setenv("EVENTS_DIR", str(tmp_path))
    if "listener" in sys.modules:
        importlib.reload(sys.modules["listener"])
    import listener
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), listener.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, tmp_path
    httpd.shutdown()
    thread.join()


def _post(port, path, body, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("POST", path, body=body, headers=headers or {})
    resp = conn.getresponse()
    status = resp.status
    resp.read()
    conn.close()
    return status


def test_missing_token_401(server):
    httpd, _ = server
    assert _post(httpd.server_address[1], "/hook", b"{}") == 401


def test_wrong_token_401(server):
    httpd, _ = server
    assert _post(httpd.server_address[1], "/hook", b"{}", {"X-Gitlab-Token": "nope"}) == 401


def test_wrong_method_404(server):
    httpd, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
    conn.request("GET", "/hook")
    assert conn.getresponse().status == 404


def test_wrong_path_404(server):
    httpd, _ = server
    assert _post(httpd.server_address[1], "/other", b"{}", {"X-Gitlab-Token": "SECRET"}) == 404


def test_oversize_body_413(server):
    httpd, _ = server
    big = b"x" * (5 * 1024 * 1024 + 1)
    assert _post(httpd.server_address[1], "/hook", big, {"X-Gitlab-Token": "SECRET"}) == 413


def test_authenticated_delivery_rewrites_last_delivery(server):
    httpd, events_dir = server
    assert _post(httpd.server_address[1], "/hook", b"{}", {"X-Gitlab-Token": "SECRET"}) == 200
    assert (events_dir / ".last_delivery").is_file()


def test_fork_pipeline_event_stored(server):
    httpd, events_dir = server
    payload = json.dumps({
        "object_kind": "pipeline",
        "object_attributes": {"id": 55, "sha": "abc", "status": "success"},
        "merge_request": {"iid": 7, "source_project_id": 90},
        "project": {"id": 21},
    }).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    files = list((events_dir / "21" / "55").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["object_attributes"]["sha"] == "abc"


def test_other_source_project_discarded(server):
    httpd, events_dir = server
    payload = json.dumps({
        "object_kind": "pipeline", "object_attributes": {"id": 55},
        "merge_request": {"iid": 7, "source_project_id": 999},
        "project": {"id": 21},
    }).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    assert not (events_dir / "21").exists()


def test_no_merge_request_discarded(server):
    httpd, events_dir = server
    payload = json.dumps({"object_kind": "pipeline", "object_attributes": {"id": 55},
                           "project": {"id": 21}}).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    assert not (events_dir / "21").exists()


def test_non_pipeline_event_discarded(server):
    httpd, events_dir = server
    payload = json.dumps({"object_kind": "push"}).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    assert list(events_dir.iterdir()) == [events_dir / ".last_delivery"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_listener.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'listener'`.

- [ ] **Step 3: Implement `docker/listener.py`**

Create `skills/odoo-deploy/docker/listener.py`:

```python
#!/usr/bin/env python3
"""Stdlib webhook receiver for odoo-deploy. Only POST /hook is served;
authenticated deliveries are stored as one file per pipeline event under
EVENTS_DIR for gitlab_ci.py's `wait` to scan — this process never talks to
the GitLab API itself."""
from __future__ import annotations

import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
FORK_PROJECT_ID = int(os.environ["FORK_PROJECT_ID"])
EVENTS_DIR = Path(os.environ.get("EVENTS_DIR", "/events"))
MAX_BODY_BYTES = 5 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/hook":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            self.send_response(413)
            self.end_headers()
            return
        body = self.rfile.read(length)

        if not hmac.compare_digest(self.headers.get("X-Gitlab-Token", ""), WEBHOOK_SECRET):
            self.send_response(401)
            self.end_headers()
            return

        self._record_delivery()
        self._store_event(body)
        self.send_response(200)
        self.end_headers()

    def _record_delivery(self) -> None:
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        marker = EVENTS_DIR / ".last_delivery"
        tmp = marker.with_suffix(".tmp")
        tmp.write_text(str(time.time_ns()), encoding="utf-8")
        os.replace(tmp, marker)

    def _store_event(self, body: bytes) -> None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return
        if data.get("object_kind") != "pipeline":
            return
        mr = data.get("merge_request")
        if not mr or mr.get("source_project_id") != FORK_PROJECT_ID:
            return
        project_id = (data.get("project") or {}).get("id")
        pipeline_id = (data.get("object_attributes") or {}).get("id")
        if project_id is None or pipeline_id is None:
            return
        received_ns = time.time_ns()
        target_dir = EVENTS_DIR / str(project_id) / str(pipeline_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = target_dir / f".{received_ns}.tmp"
        tmp_path.write_bytes(body)
        os.replace(tmp_path, target_dir / f"{received_ns}.json")

    def log_message(self, fmt, *args) -> None:
        pass  # default logging echoes the request line; keep it quiet


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/test_listener.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Create `docker/compose.yml`**

Create `skills/odoo-deploy/docker/compose.yml`:

```yaml
services:
  cloudflared:
    image: cloudflare/cloudflared:2025.9.1
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN}

  listener:
    image: python:3.12-slim
    restart: unless-stopped
    user: "${LISTENER_UID}:${LISTENER_GID}"
    environment:
      WEBHOOK_SECRET: ${WEBHOOK_SECRET}
      FORK_PROJECT_ID: ${FORK_PROJECT_ID}
      EVENTS_DIR: /events
    volumes:
      - ./listener.py:/listener.py:ro
      - ./events:/events
    command: ["python3", "/listener.py"]
```

Confirm `cloudflare/cloudflared:2025.9.1` is a real published tag before
committing (`docker manifest inspect cloudflare/cloudflared:2025.9.1`); pin
whatever the current stable release tag actually is instead if not.

- [ ] **Step 6: Create `docker/.env.example`**

Create `skills/odoo-deploy/docker/.env.example`:

```
# Copy to .env (chmod 600) and fill in TUNNEL_TOKEN/HOOK_HOSTNAME — see
# README.md "Cloudflare tunnel". The remaining keys (WEBHOOK_SECRET,
# FORK_PROJECT_ID, LISTENER_UID, LISTENER_GID) are filled in automatically
# by `gitlab_ci.py setup` — leave them blank here.
TUNNEL_TOKEN=
HOOK_HOSTNAME=
WEBHOOK_SECRET=
FORK_PROJECT_ID=
LISTENER_UID=
LISTENER_GID=
```

- [ ] **Step 7: Add the events directory to `.gitignore`**

Add to this repo's root `.gitignore` (`.env` under `docker/` is already
covered by the existing bare `.env` pattern near the top of the file):

```
skills/odoo-deploy/docker/events/
```

- [ ] **Step 8: Run the full odoo-deploy test suite**

Run: `cd skills/odoo-deploy && python3 -m pytest tests/ -v`
Expected: PASS (all tests from Tasks 1–8).

- [ ] **Step 9: Commit**

```bash
git add skills/odoo-deploy/docker/listener.py skills/odoo-deploy/docker/compose.yml \
        skills/odoo-deploy/docker/.env.example skills/odoo-deploy/tests/test_listener.py .gitignore
git commit -m "feat(odoo-deploy): webhook listener + docker compose stack

listener.py: stdlib http.server, POST /hook only, X-Gitlab-Token
checked with hmac.compare_digest, oversize bodies rejected before
reading, one file per fork-MR pipeline event written atomically under
EVENTS_DIR; everything else discarded with 200 so GitLab never retries.
compose.yml runs it alongside a named cloudflared tunnel, both
restart: unless-stopped."
```

---

### Task 9: `SKILL.md` + `README.md`

**Files:**
- Create: `skills/odoo-deploy/SKILL.md`
- Create: `skills/odoo-deploy/README.md`

**Interfaces:**
- Produces: the skill's entry point (`SKILL.md`, loaded by name or via
  `/odoo-deploy`) and its one-time human setup guide (`README.md`, the
  target of every `check-setup` failure's `fix` field from Task 7).
- Consumes: every `gitlab_ci.py` subcommand from Tasks 1–7 by name and flag
  shape; `skills/odoo-debug/playbooks/test-failure-log-triage.md` (existing
  file, referenced not modified); `CLAUDE.odoo.md`'s "Determine the
  validation scope" section (existing, referenced not modified).

No tests — these are documentation files. Both must still contain zero
placeholders: every command shown must be the exact flag shape Tasks 1–7
actually implemented.

- [ ] **Step 1: Create `skills/odoo-deploy/SKILL.md`**

```markdown
---
name: odoo-deploy
description: >-
  Push committed, locally-verified Odoo implementation work to GitLab, open
  or reuse the merge request, and drive the MR pipeline to green — fetching
  failed-job logs, diagnosing, fixing, and re-pushing on failure, up to the
  escalation limits below. Offer this once local verification passes for the
  current branch; also invocable as /odoo-deploy [--target BRANCH]. Never
  merges, approves, or enables auto-merge.
---

# odoo-deploy — push, open MR, drive GitLab CI to green

## Resolve the skill directory first

Every script path below is written as `$SKILL_DIR/scripts/gitlab_ci.py`. Set
`SKILL_DIR` to this skill's own base directory — the directory containing
this SKILL.md (reported as "Base directory for this skill" when loaded, or
find it with `dirname` on wherever this file was read from) — same
convention as `skills/odoo-wlc/SKILL.md`.

Working directory for every `gitlab_ci.py` call: the Odoo workspace (where
`config/project.json` lives, written by `odoo setup`). `gitlab_ci.py`
resolves `git_root` from that file and runs every git command there — the
workspace and the git repo are not the same directory (see
`CLAUDE.odoo.md` "File locations").

Scratch directory: `<workspace>/tmp/odoo-deploy/<branch-with-/-as-->/`
(e.g. branch `feature/x` → `tmp/odoo-deploy/feature-x/`). Keyed by branch,
not by MR IID, so a re-run finds it before the MR IID is known (after the
first `push`, it is).

## 1. Offer

Only after this session's implementation work is committed and locally
verified (per the project's own verification rules — `odoo verify`, tests
via `agy`/`odoo runtime-test` over the in-scope modules). Ask once:

> Push to GitLab and drive CI to green?

No → stop, do nothing further. Yes → the rest of this flow, including every
fix commit and fix-push in the loop below, is authorized by that one answer;
never ask again mid-loop.

## 2. Setup gate

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py check-setup
```

Exit 11 → stop. Relay the failed checks (`id`, `detail`, `fix`) to the user
verbatim — `fix` names the exact README section or command to run. Never
start the loop on an incomplete setup; `check-setup` exit 11 is not an
escalation (the loop never started).

## 3. Preflight

1. Dirty tracked tree → stop: "commit or stash first" (per
   `skills/odoo/playbooks/git-workflow.md`).
2. Confirm local verification evidence exists from *this session* — not
   assumed, not re-run speculatively. No evidence → run verification first;
   never push unverified work.
3. Lint:

   ```bash
   python3 $SKILL_DIR/scripts/gitlab_ci.py lint --target <target>
   ```

   `skipped: true` → continue. Findings with `in_branch: false` → escalate
   now, before any push (rule 3 below — pre-existing, out of scope). Findings
   with `in_branch: true` → fix them, re-verify, commit
   `[FIX] <module>: ruff` with explicit paths. This is not a fix-push (no
   loop-cap consumed) — it happens before `push` is ever called.

## 4. Push

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py push --target <target>
```

Resuming after `<scratch>/loop.md` already exists (a prior run's fix-push,
or recovery after a dropped webhook — see "Recovery"):

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py push --target <target> --no-rebase
```

Exit 4 (rebase conflict) or 5 (push rejected) → escalate (rule 7). On
success, **print the MR URL to the user immediately** — don't wait for the
pipeline. Record `mr_iid`, `sha`, and `since` (when `pushed: true`) from the
output; append this iteration to `<scratch>/loop.md`.

## 5. Wait

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py wait --mr <mr_iid> --sha <sha> [--since <since>]
```

Run this as a **background** Bash command — the session is re-invoked when
it exits. Pass `--since` only when the triggering `push`/`retry-job` output
included one.

## 6. Green (exit 0)

Final report to the user: MR URL, pipeline URL, every fix commit made (if
any), iterations used, and "review and merge it yourself" (see "No-merge
rule"). Send the push notification and:

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py notify \
  --text "MR !<mr_iid> green — review and merge it yourself: <mr_url>"
```

Then:

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py clean --mr <mr_iid>
```

and delete `<scratch>`.

## 7. Red (exit 1)

1. Fetch logs:

   ```bash
   python3 $SKILL_DIR/scripts/gitlab_ci.py fetch-logs \
     --project <pipeline_project_id> --pipeline <pipeline_id> --out <scratch>/pipeline-<id>/
   ```

   A failed `ruff` job in the manifest → also re-run `gitlab_ci.py lint`
   (the trace has no findings — CI writes them to `ruff-output`, not an
   artifact).

2. Check every escalation rule below against the fetch-logs manifest,
   traces, and lint output, **before** touching any code. Any rule firing →
   stop, go to "Escalation".

3. Triage using odoo-debug's
   [test-failure-log-triage](../odoo-debug/playbooks/test-failure-log-triage.md)
   playbook: one failure per traceback, each classified (app bug / wrong
   test / environment). Lint: one finding per file + rule.

4. Reproduce locally (re-run the failing tests, or `gitlab_ci.py lint`), fix
   through the owning skill (`odoo-model`, `odoo-view`, `odoo-test`, ...),
   re-verify per the project's own rules, including `lint` again.

5. Commit: `[FIX] <module>: <desc>` with explicit paths — never `git add -A`.

6. Push again and loop back to step 5 (Wait):

   ```bash
   python3 $SKILL_DIR/scripts/gitlab_ci.py push --target <target> --no-rebase
   ```

   Fix iterations never rebase — the CI delta between iterations is caused
   by the fix just made, not by new upstream commits.

## 8. Loop log

Every iteration appends one entry to `<scratch>/loop.md`: iteration number,
pipeline id + URL, failure signature(s) (see below), fix commit SHA. The
3-fix-push cap, the repeated-failure-signature check, and resume detection
(step 4's `--no-rebase` branch) all read this file — it is what lets the
loop survive a conversation compaction.

## No-merge rule

Never merge, approve, or enable auto-merge (`merge_when_pipeline_succeeds`)
on the MR — not through `gitlab_ci.py`, `glab`, `curl`, or the web UI.
`gitlab_ci.py` has no merge or approve command; do not add one. Merging is
the user's decision after reviewing the green MR.

## Failure signatures

Used by escalation rule 4 ("same failure repeats"):
- pytest failure: `<job>::<test node id>`
- lint finding: `<job>::<file>::<rule code>` (no line number — it shifts)
- anything else: `<job>::<first error line of the trace>`

## Scope

In-scope modules = addons touched by
`git diff --name-only upstream/<target>...HEAD` plus their transitive
reverse dependencies (`CLAUDE.odoo.md`, "Determine the validation scope"). A
pytest failure's module is the path segment after `custom-addons/` in its
node id.

## Escalation

Any rule below firing: stop the loop, keep `<scratch>` and this MR's events
(do **not** run `clean`), report MR URL, pipeline URL, the rule that fired,
and evidence (paths into the saved logs). Send the push notification and:

```bash
python3 $SKILL_DIR/scripts/gitlab_ci.py notify \
  --text "MR !<mr_iid> stopped (rule <n>) — needs you: <mr_url>"
```

Then ask the user how to proceed.

1. 3 fix-pushes already made (count entries in `<scratch>/loop.md`).
2. Infra failure — `failure_reason` in the fetch-logs manifest is not
   `script_failure`, or the trace shows a Vault, docker-pull, network, or
   disk-space error:

   ```bash
   python3 $SKILL_DIR/scripts/gitlab_ci.py retry-job --project <id> --job <job_id>
   ```

   once per job. The same job failing on infra again on the next `wait` →
   escalate.
3. A failure outside scope: a module not in the in-scope set (above), or a
   lint finding in a file the branch did not touch (`in_branch: false` —
   preflight's `lint` run in step 3 already catches most of these before
   any push, but a red pipeline can surface one CI's `ruff` found that
   preflight's config diverged from).
4. A failure signature (above) already recorded in `loop.md` for an earlier
   iteration.
5. The fix would change a test assertion or expected value, a migration
   script, ACL/record rules, or `.po`/`.pot` files.
6. The failure cannot be reproduced locally and the log does not pin down
   the cause.
7. `push` exits 4 or 5; `wait` exits 2 or 3; any `gitlab_ci.py` command
   exits 10.

## Recovery

`wait` exiting 3 with `reason: no_pipeline`, or a dropped webhook (machine
was off, tunnel down), is not itself an escalation trigger — GitLab does not
re-send a failed delivery, but re-running `/odoo-deploy` on the same branch
recovers the result through `wait`'s own initial GET of the MR's
`head_pipeline`, which does not depend on the webhook having arrived at all.
Resume via step 4's `--no-rebase` push (a no-op when already up to date),
then step 5's `wait` again.
```

- [ ] **Step 2: Create `skills/odoo-deploy/README.md`**

```markdown
# odoo-deploy setup

One-time setup for driving GitLab MR pipelines to green through a
webhook-delivered result. Each section below is what a `check-setup`
failure's `fix` field points to.

## 1. Prerequisites

- Owner or Maintainer access (GitLab access level ≥ 40) on the **upstream**
  project — the one the MR pipeline actually runs in, even for a fork MR
  (see the design spec's "Environment facts" for why).
- Docker enabled at boot (`systemctl is-enabled docker` → `enabled`) and
  your user in the `docker` group (`groups | grep docker`) — the compose
  stack must survive a reboot without anyone logging in to start it.
- `uvx` on `PATH` (part of [uv](https://docs.astral.sh/uv/)) — used by
  `gitlab_ci.py lint` to run a pinned `ruff` version without installing it
  into any project venv.
- Access to the `vdx.vn` Cloudflare Zero Trust account, with permission to
  create tunnels and public hostnames in that zone.

## 2. Cloudflare tunnel

1. In the Cloudflare Zero Trust dashboard, create a **remotely managed**
   tunnel (not a quick tunnel — its URL changes on every run, which would
   mean re-creating the GitLab hook every time).
2. Add a public hostname, e.g. `odoo-deploy.vdx.vn`, routing to
   `http://listener:8080` (the `listener` service name from
   `docker/compose.yml` — Docker's internal DNS resolves it; this is not
   `localhost`).
3. Copy the tunnel token from the dashboard.
4. In this skill's directory:

   ```bash
   cp docker/.env.example docker/.env
   chmod 600 docker/.env
   ```

   Edit `docker/.env` and set:

   ```
   TUNNEL_TOKEN=<the token from step 3>
   HOOK_HOSTNAME=odoo-deploy.vdx.vn
   ```

   Leave every other key in `docker/.env` blank — `gitlab_ci.py setup`
   (section 5) fills them in.

## 3. Project config

From the Odoo workspace root (where `config/project.json` lives):

```bash
odoo setup --force --setup-telegram
```

This (re)writes `config/project.json`, adding `git_root`/`gitlab_url`
(discovered from the addons checkout's git remotes) and, via
`--setup-telegram`, `telegram_channel`/`telegram_token` (prompted
interactively, then verified against the real Telegram Bot API). Run
without `--setup-telegram` only if those two fields are already set some
other way — `check-setup` check `g` needs both.

## 4. GitLab token

Nothing to do if `git push` to `origin` already works from this machine —
the same credential (from `~/.gitlab` or your normal git credential helper,
e.g. `glab`'s) is reused for the GitLab REST API calls.

Otherwise, create a Personal Access Token on `gitlab.vdx.vn` with the `api`
scope, then add it to `~/.gitlab`:

```ini
[gitlab]
https://gitlab.vdx.vn/ = <your-token>
```

## 5. Run setup

From the Odoo workspace root:

```bash
python3 skills/odoo-deploy/scripts/gitlab_ci.py setup
```

This fills in the remaining `docker/.env` keys, brings up the `cloudflared`
+ `listener` containers (`restart: unless-stopped` — they survive a reboot
once Docker itself is enabled at boot), and creates/updates a single
pipeline-events-only hook on the upstream project. It ends by running
`check-setup` and embedding the result under `check` — expect
`check.ok: true`. If it isn't, see Troubleshooting below for the specific
failing check id.

## 6. Troubleshooting

Each row is a `check-setup` check id.

| id | Checks | If it fails |
|---|---|---|
| a | `config/project.json` has `git_root`/`gitlab_url`; `origin`+`upstream` git remotes exist; `upstream`'s host matches `gitlab_url` | Re-run section 3; confirm the addons checkout actually has both remotes (`git remote -v`) |
| b | A GitLab token resolves and `GET /user` succeeds | Section 4 |
| c | `docker/.env` has all six keys | Re-run section 2, then section 5 (`setup` fills the automatic ones) |
| d | `docker compose ps` shows both `cloudflared` and `listener` running | `docker compose -f skills/odoo-deploy/docker/compose.yml logs` — a crash-looping container usually means a bad `TUNNEL_TOKEN` or a `WEBHOOK_SECRET`/`FORK_PROJECT_ID` missing from `.env` |
| e | The upstream project has exactly one hook at `https://$HOOK_HOSTNAME/hook`, `pipeline_events: true`, `alert_status: executable` | Re-run section 5 (`setup` creates/updates it); a non-`executable` `alert_status` means GitLab is failing to deliver — check `d` and the Cloudflare dashboard first |
| f | `uvx` on `PATH` | Section 1 |
| g | `telegram_channel`/`telegram_token` in `config/project.json`; Telegram `getMe` succeeds | Re-run section 3 with `--setup-telegram` |
| h | A real test delivery (`POST .../hooks/:id/test/pipeline_events`) reaches the listener within 15s | Confirm the Cloudflare public hostname is routed and the tunnel container (`d`) is actually connected — check the Cloudflare Zero Trust dashboard's tunnel status |

## Never

The agent driving this skill never merges, approves, or enables auto-merge
on any MR — see `SKILL.md` "No-merge rule". This setup only grants it push
and MR-open access; merging stays a human decision.
```

- [ ] **Step 3: Commit**

```bash
git add skills/odoo-deploy/SKILL.md skills/odoo-deploy/README.md
git commit -m "docs(odoo-deploy): SKILL.md flow and README setup guide

SKILL.md sequences the gitlab_ci.py commands from Tasks 1-7 into the
offer -> setup-gate -> preflight -> push -> wait -> green|red loop,
with the no-merge rule, failure signatures, scope, and all 7
escalation rules. README.md is the setup guide check-setup's fix
field points into, one section per check id."
```

---

### Task 10: Wire `odoo-deploy` into the existing `odoo` skill and `CLAUDE.odoo.md`

**Files:**
- Modify: `skills/odoo/playbooks/git-workflow.md`
- Modify: `skills/odoo/SKILL.md`
- Modify: `claude-code/CLAUDE.odoo.md`

**Interfaces:** none — these are three small, independent text edits to
existing files, each already read in full during this plan's research (see
plan header). No new function or script surface.

No tests — markdown/documentation edits only. Verification is a manual read
of each diff against the "no placeholders" rule below.

- [ ] **Step 1: Replace `git-workflow.md`'s "Push + open the MR" bullet**

The current bullet (`skills/odoo/playbooks/git-workflow.md`, in the "Steps"
section) describes a push/MR script that doesn't exist in this repo. Replace
it — and only it, leave every other bullet in "Steps" untouched — with:

Old text (the entire bullet, starting at `- [ ] Push + open the MR only if`
through `Report the MR URL to the user — don't just say "pushed."`):

```markdown
- [ ] Push + open the MR only if the user explicitly asked this session — never as
  an automatic follow-on. Order: fetch `upstream` → checkout/create the local
  working branch → `git add -A` + commit (skipped if clean) → rebase onto
  `upstream` → force-with-lease push to `origin` → open/reuse a cross-project MR
  `origin/<branch>` → `upstream/<branch>`, print the MR URL. On rebase conflict the
  script exits and tells you to resolve, then `git rebase --continue` and re-run
  (it skips the already-done commit and proceeds from rebase). Provider
  authentication needs an access token (`api` scope) exported — one-time setup;
  check `[ -n "$GITLAB_TOKEN" ]` first, don't `echo` the value.

  Report the MR URL to the user — don't just say "pushed."
```

New text:

```markdown
- [ ] Push + open the MR: once implementation work is committed and
  verified, offer the separate `odoo-deploy` skill — ask once, "Push to
  GitLab and drive CI to green?" No → stop here; this playbook's job
  (commit) is already done. Yes → hand off to `odoo-deploy`'s own flow
  (push, open/reuse the MR, wait on the pipeline, fix-and-repush loop on
  failure); never push or open the MR directly from this playbook, and
  never as an automatic follow-on without that explicit "yes".
```

- [ ] **Step 2: Mention `odoo-deploy` on `SKILL.md`'s process-playbook line**

`skills/odoo/SKILL.md`'s "Dispatch table" section ends with this paragraph
(the "process-playbook line"):

Old text:

```markdown
Process playbooks live in this skill, under `playbooks/` — run
[task-evaluation](playbooks/task-evaluation.md) first on any task; then as
triggered: [diagnosis-before-implementation](playbooks/diagnosis-before-implementation.md),
[git-workflow](playbooks/git-workflow.md) (commit; push/MR only when asked),
[pr-review](playbooks/pr-review.md), [session-review](playbooks/session-review.md).
```

New text:

```markdown
Process playbooks live in this skill, under `playbooks/` — run
[task-evaluation](playbooks/task-evaluation.md) first on any task; then as
triggered: [diagnosis-before-implementation](playbooks/diagnosis-before-implementation.md),
[git-workflow](playbooks/git-workflow.md) (commit; offers the separate
`odoo-deploy` skill for push/MR/CI once verified), [pr-review](playbooks/pr-review.md),
[session-review](playbooks/session-review.md).
```

- [ ] **Step 3: Add a dispatch-table row in `CLAUDE.odoo.md`**

`claude-code/CLAUDE.odoo.md`'s "Skill dispatch table" section:

Old text:

```markdown
| Task | Skill |
| --- | --- |
| Python: models, fields, constraints, security, wizards, controllers | `odoo-model` |
| XML: views, inheritance, widgets, QWeb reports, assets | `odoo-view` |
| Writing/running tests | `odoo-test` |
| Triage failing behavior, live/DB inspection | `odoo-debug` |
| Cross-major port (17/18/19), migration scripts | `odoo-upgrade` |
| Translation / Weblate `.po` round-trip | `odoo-wlc` |
```

New text:

```markdown
| Task | Skill |
| --- | --- |
| Python: models, fields, constraints, security, wizards, controllers | `odoo-model` |
| XML: views, inheritance, widgets, QWeb reports, assets | `odoo-view` |
| Writing/running tests | `odoo-test` |
| Triage failing behavior, live/DB inspection | `odoo-debug` |
| Cross-major port (17/18/19), migration scripts | `odoo-upgrade` |
| Translation / Weblate `.po` round-trip | `odoo-wlc` |
| Push to GitLab, open MR, drive CI to green | `odoo-deploy` |
```

- [ ] **Step 4: Review the three diffs**

`git diff skills/odoo/playbooks/git-workflow.md skills/odoo/SKILL.md claude-code/CLAUDE.odoo.md`
— confirm each changed hunk matches exactly the Old→New text above and
nothing else in these three files moved.

- [ ] **Step 5: Commit**

```bash
git add skills/odoo/playbooks/git-workflow.md skills/odoo/SKILL.md claude-code/CLAUDE.odoo.md
git commit -m "docs(odoo): route push/MR/CI through the new odoo-deploy skill

git-workflow.md's push bullet described a script that never existed
in this repo; it now offers odoo-deploy (ask once) instead. SKILL.md
and CLAUDE.odoo.md gain a pointer/dispatch-table row so the new skill
is discoverable from the existing odoo skill router."
```

## Self-Review

**1. Spec coverage** — every "Files: New in this repo" entry has a task:
`SKILL.md`/`README.md` → Task 9; `scripts/gitlab_ci.py` → Tasks 1–7;
`docker/compose.yml`/`docker/listener.py`/`docker/.env.example` → Task 8;
`tests/test_gitlab_ci.py` → Tasks 1–7; `tests/test_listener.py` → Task 8.
Every "Files: Edited in this repo" bullet has a task: `.gitignore` → Task 8
Step 7; `git-workflow.md`, `odoo/SKILL.md`, `CLAUDE.odoo.md` → Task 10.
Every `## Script: scripts/gitlab_ci.py` subsection has a task: `setup`/
`check-setup` → Task 7; `lint` → Task 5; `push` → Task 2; `wait` → Task 3;
`fetch-logs` → Task 4; `retry-job`/`notify`/`clean` → Task 6. Every row of
the exit-code table appears in at least one task (0/1/2 in Tasks 2–3/5;
3 in Task 3; 4/5 in Task 2; 10 via `main()`'s wrapper, Task 2; 11 in Task 7).
The HTTP retry policy, `User-Agent`, one-JSON-line-per-command, and
no-merge rule are all Global Constraints, applied by every task that makes
an HTTP call or touches the MR. The "Configuration" table's `config/project.json`
row (`git_root`/`gitlab_url`) is the companion `odoo-cli` plan
(`docs/superpowers/plans/2026-09-11-odoo-cli-git-discovery.md`), referenced
in this plan's Spec header, not duplicated here. Acceptance tests (a)/(b)/(c)
are manual, run by the user on a throwaway branch after both plans ship —
not converted into automated tasks, since they need a real GitLab instance
and a real pipeline run; `README.md` (Task 9) and `SKILL.md`'s flow (Task 9)
are what those acceptance tests exercise.

**2. Placeholder scan** — the one intentionally-flagged gap is Task 5's
`rewrite_ruff_ignore` (the real `scripts/utils.sh` transform is outside this
repo and unverified at plan-writing time); it is called out explicitly with
a required verification step, not silently assumed. No other `TBD`/"add
error handling"/"similar to Task N" patterns found on re-scan.

**3. Type consistency** — every `cmd_*` function returns a plain `dict`
(JSON-able); every subcommand's flag names match its `cmd_*` function's
parameter names 1:1 (`--mr` → `mr_iid`, `--project`/`--pipeline` →
`project_id`/`pipeline_id`, `--out` → `out_dir`, `--job` → `job_id`, `--text`
→ `text`, `--target` → `target`). `resolve_gitlab_token`, `api_request`,
`git_remote_project_path`, `gitlab_project_id`, `events_dir`, `skill_dir`,
and `USER_AGENT` are defined once (Tasks 1–4) and only ever consumed,
never redefined, by every later task. `main()`'s `SystemExit`-code-vs-message
convention (message-only = mapped to exit 10; `int` = passed through) is
established once in Task 2 and used identically by every later task's exit
paths (`push` 4/5, `wait` 3, `lint` 1, `setup`/`check-setup` 11).

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-11-odoo-deploy-skill.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
