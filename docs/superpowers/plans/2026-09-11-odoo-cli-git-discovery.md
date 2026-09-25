# odoo-cli git_root/gitlab_url Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `odoo setup` (odoo-cli) to discover a project's git checkout
root and GitLab base URL, so the `odoo-deploy` skill (a separate plan, in the
`ai` repo) can locate `git_root`/`gitlab_url` in `config/project.json` instead
of asking the user.

**Architecture:** Two pure, bounded-cost probes (`find_git_root`,
`find_gitlab_url`) added to `setup_discovery.py` alongside the existing
`find_*` helpers, wired into `discover()`'s `proposed` dict exactly like every
other field. No change to `cli/commands/setup.py` — it already writes whatever
`discovery.fields` contains, and already tolerates missing fields (they land
in `discovery.missing` and are simply left out of the written file).

**Tech Stack:** Python 3.10+ stdlib only (`subprocess`, `re`, `pathlib`);
pytest with real `git init`/`git remote add` in `tmp_path` (matches
`tests/test_verify.py`'s `_git_init` pattern — this codebase does not mock
`git` subprocess calls in discovery/verify tests).

**Spec:** `docs/superpowers/specs/2026-09-11-odoo-deploy-design.md` (this
plan implements only the "Edited in `odoo-cli`" bullets and the
`git_root`/`gitlab_url` rows of the "Configuration" table).

**Repo:** All file paths below are relative to `/home/xmars/dev/vdx-vn/odoo-cli`
(a separate repo/commit from the `odoo-deploy` skill plan).

## Global Constraints

- Stdlib only — no new dependency (matches every other `find_*` probe in
  `setup_discovery.py`).
- Bounded-depth/bounded-cost probes only: at most two `git` subprocess calls
  per project (`rev-parse --show-toplevel`, `remote get-url`) — no repo-wide
  walk.
- `git_root` source: `git rev-parse --show-toplevel` run with `cwd=addons_dir`
  (the already-discovered `extra-addons` dir) — **not** `repo_root`, because
  the Odoo core checkout (`repo_root`) is typically a different git repo (or
  no repo at all) from the addons checkout.
- `gitlab_url` source: scheme + host of the `upstream` remote, falling back to
  `origin` when `upstream` doesn't exist; SSH remotes (`git@host:path` or
  `ssh://git@host/path`) map to `https://<host>` (never keep the `ssh://`
  scheme or the `git@` userinfo — GitLab's REST API is always HTTPS).
- A missing/undetectable field is reported via `Discovery.missing`, exactly
  like every other field — never raise, never guess.

---

### Task 1: `git_root` + `gitlab_url` discovery

**Files:**
- Modify: `src/odoo_cli/setup_discovery.py`
- Modify: `config/project.json.example`
- Modify: `README.md:123-233` (field docs)
- Test: `tests/test_setup_discovery.py`

**Interfaces:**
- Produces: `find_git_root(addons_dir: Path | None) -> Path | None` and
  `find_gitlab_url(git_root: Path | None) -> str | None`, both added to
  `setup_discovery.py`'s public surface (same visibility as `find_odoo_sources`,
  `find_odoo_version`). `discover()` gains two new keys in its return value's
  `.fields`/`.missing`: `git_root`, `gitlab_url`.
- Consumes: nothing new — `find_git_root` takes the `extra_addons` value
  `discover()` already computes; `find_gitlab_url` takes the `git_root` value
  `find_git_root` just returned.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_setup_discovery.py` (after the existing `_core` helper, so
the new tests can also use `_project`/`_core`):

```python
def _git_init(path: Path, remotes: dict[str, str] | None = None) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    for name, url in (remotes or {}).items():
        subprocess.run(["git", "remote", "add", name, url], cwd=path, check=True)


def test_find_git_root_from_addons_dir(tmp_path: Path) -> None:
    project = _project(tmp_path)
    addons_dir = project / "sources" / "extra-addons"
    _git_init(project)  # .git at the project root, above addons_dir

    assert sd.find_git_root(addons_dir) == project


def test_find_git_root_none_outside_a_repo(tmp_path: Path) -> None:
    project = _project(tmp_path)
    addons_dir = project / "sources" / "extra-addons"

    assert sd.find_git_root(addons_dir) is None


def test_find_git_root_none_when_addons_dir_missing(tmp_path: Path) -> None:
    assert sd.find_git_root(None) is None
    assert sd.find_git_root(tmp_path / "nope") is None


def test_find_gitlab_url_prefers_upstream_https(tmp_path: Path) -> None:
    _git_init(tmp_path, {
        "origin": "https://gitlab.vdx.vn/truong/sca.git",
        "upstream": "https://gitlab.vdx.vn/sungroup/sca",
    })
    assert sd.find_gitlab_url(tmp_path) == "https://gitlab.vdx.vn"


def test_find_gitlab_url_falls_back_to_origin(tmp_path: Path) -> None:
    _git_init(tmp_path, {"origin": "https://gitlab.vdx.vn/truong/sca.git"})
    assert sd.find_gitlab_url(tmp_path) == "https://gitlab.vdx.vn"


def test_find_gitlab_url_maps_ssh_scp_form(tmp_path: Path) -> None:
    _git_init(tmp_path, {"upstream": "git@gitlab.vdx.vn:sungroup/sca.git"})
    assert sd.find_gitlab_url(tmp_path) == "https://gitlab.vdx.vn"


def test_find_gitlab_url_maps_ssh_url_form(tmp_path: Path) -> None:
    _git_init(tmp_path, {"upstream": "ssh://git@gitlab.vdx.vn/sungroup/sca.git"})
    assert sd.find_gitlab_url(tmp_path) == "https://gitlab.vdx.vn"


def test_find_gitlab_url_none_without_remotes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    assert sd.find_gitlab_url(tmp_path) is None


def test_find_gitlab_url_none_when_git_root_none(tmp_path: Path) -> None:
    assert sd.find_gitlab_url(None) is None


def test_discover_reports_git_root_and_gitlab_url(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _git_init(project, {"upstream": "https://gitlab.vdx.vn/sungroup/sca"})

    discovery = sd.discover(project)

    assert discovery.fields["git_root"] == str(project)
    assert discovery.fields["gitlab_url"] == "https://gitlab.vdx.vn"


def test_discover_reports_git_root_and_gitlab_url_missing_outside_repo(tmp_path: Path) -> None:
    project = _project(tmp_path)

    discovery = sd.discover(project)

    assert "git_root" in discovery.missing
    assert "gitlab_url" in discovery.missing
```

Also add `import subprocess` to the test file's import block at the top
(alongside the existing `from pathlib import Path`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/xmars/dev/vdx-vn/odoo-cli && .venv/bin/pytest tests/test_setup_discovery.py -k "git_root or gitlab_url" -v`
Expected: FAIL with `AttributeError: module 'odoo_cli.setup_discovery' has no attribute 'find_git_root'` (and similarly for `find_gitlab_url`, and for the two `discover()` tests once the first two are fixed).

- [ ] **Step 3: Implement `find_git_root` and `find_gitlab_url`**

Add `import subprocess` to `src/odoo_cli/setup_discovery.py`'s import block
(after `import shutil`, before `from dataclasses import ...`).

Add after `find_odoo_sources` (before `find_odoo_version`, so the new probes
sit next to the other filesystem/subprocess probes):

```python
def find_git_root(addons_dir: Path | None) -> Path | None:
    """The git checkout containing `addons_dir` — usually a different repo
    from the Odoo core checkout (`repo_root`), so this runs `git` with
    `cwd=addons_dir`, never `cwd=repo_root`."""
    if addons_dir is None or not addons_dir.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=addons_dir, capture_output=True, text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


_SSH_REMOTE_RE = re.compile(r"^(?:ssh://)?git@([^:/]+)[:/]")
_HTTPS_REMOTE_RE = re.compile(r"^(https?)://(?:[^@/]+@)?([^/]+)/")


def find_gitlab_url(git_root: Path | None) -> str | None:
    """Scheme + host of the `upstream` remote, else `origin`; SSH remotes
    (`git@host:path` or `ssh://git@host/path`) map to `https://<host>` —
    GitLab's REST API is always HTTPS regardless of how the remote is cloned."""
    if git_root is None:
        return None
    for remote_name in ("upstream", "origin"):
        result = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            cwd=git_root, capture_output=True, text=True,
        )
        if result.returncode != 0:
            continue
        url = result.stdout.strip()
        match = _HTTPS_REMOTE_RE.match(url)
        if match:
            return f"{match.group(1)}://{match.group(2)}"
        match = _SSH_REMOTE_RE.match(url)
        if match:
            return f"https://{match.group(1)}"
    return None
```

Wire both into `discover()` — add after the existing
`community, enterprise = find_odoo_sources(repo_root, rc)` line:

```python
    git_root = find_git_root(extra_addons)
    gitlab_url = find_gitlab_url(git_root)
```

And add two entries to the `proposed` dict, after `"odoo_enterprise_path"`:

```python
        "odoo_enterprise_path": str(enterprise) if enterprise else None,
        "git_root": str(git_root) if git_root else None,
        "gitlab_url": gitlab_url,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/xmars/dev/vdx-vn/odoo-cli && .venv/bin/pytest tests/test_setup_discovery.py -v`
Expected: PASS, all tests including the pre-existing ones (the new fields
must not break `test_discover_full_project`'s exact-field assertions — that
test only asserts specific keys are present via `==`/`in`, and never asserts
the full field set, so it stays green unmodified).

- [ ] **Step 5: Update `config/project.json.example`**

```json
{
  "repo_root": "/path/to/your/project/odoo_repo",
  "pythonpath": "/path/to/your/project/odoo_repo/sources",
  "rc": "/path/to/your/project/odoo_config_test",
  "python": "/path/to/your/venv/bin/python",
  "db": "your_test_db",
  "test_scope": "sources/extra-addons",
  "addons_dir": "/path/to/your/project/odoo_repo/sources/extra-addons",
  "no_translate_file": "/path/to/your/project/no-translate.txt",
  "git_root": "/path/to/your/project/odoo_repo/addons",
  "gitlab_url": "https://gitlab.example.com",
  "telegram_channel": "-1001234567890",
  "telegram_token": "123456789:AAExampleTokenNotReal-doNotUse"
}
```

- [ ] **Step 6: Document the two fields in `README.md`**

In the manual-setup field list (around `README.md:228-233`, right after the
`odoo_enterprise_path` bullet), add:

```markdown
   - `git_root` — the git checkout root containing `addons_dir` (from `git
     rev-parse --show-toplevel` run inside it); usually a different repo from
     `repo_root`/the Odoo core checkout. Used by the `odoo-deploy` skill, not
     by any `odoo-cli` command directly.
   - `gitlab_url` — scheme + host of that checkout's `upstream` git remote
     (falling back to `origin`), e.g. `https://gitlab.example.com`; SSH
     remotes are mapped to their `https://` host. Also used only by the
     `odoo-deploy` skill.
```

- [ ] **Step 7: Run the full test suite**

Run: `cd /home/xmars/dev/vdx-vn/odoo-cli && .venv/bin/pytest tests/ -v`
Expected: PASS — no regressions in `test_setup_command.py` or elsewhere
(neither field is read by any existing command, so nothing else can break).

- [ ] **Step 8: Commit**

```bash
cd /home/xmars/dev/vdx-vn/odoo-cli
git add src/odoo_cli/setup_discovery.py config/project.json.example README.md tests/test_setup_discovery.py
git commit -m "feat: discover git_root/gitlab_url in odoo setup

For the odoo-deploy skill: the addons checkout is usually a different
git repo from the Odoo core checkout, so git_root is probed from
addons_dir rather than repo_root; gitlab_url is the upstream (falling
back to origin) remote's scheme+host, with SSH remotes mapped to https."
```

## Self-Review

**1. Spec coverage:**
- "`git_root` | `git rev-parse --show-toplevel` of `addons_dir`" — Task 1, `find_git_root`. ✓
- "`gitlab_url` | scheme + host of the `upstream` remote (else `origin`); SSH remotes map to `https://<host>`" — Task 1, `find_gitlab_url`. ✓
- "`src/odoo_cli/setup_discovery.py` — discover `git_root` and `gitlab_url`" — Task 1, Step 3. ✓
- "`tests/test_setup_discovery.py` — cases below" (`git_root` from `addons_dir`; `gitlab_url` from SSH and HTTPS `upstream`, `origin` fallback; non-git tree → both reported missing) — Task 1, Step 1. ✓
- "`config/project.json.example`, `README.md` — document both fields" — Task 1, Steps 5–6. ✓
- No `cli/commands/setup.py` change is listed in the spec's file table, and none is needed (see Architecture above).

**2. Placeholder scan:** none found — every step has literal code or literal doc text.

**3. Type consistency:** `find_git_root` returns `Path | None`; `find_gitlab_url` takes that same `Path | None` and returns `str | None`; `discover()` stores both as `str | None` in `proposed`, matching every other path-valued field's `str(...) if ... else None` convention already in the file.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-11-odoo-cli-git-discovery.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
