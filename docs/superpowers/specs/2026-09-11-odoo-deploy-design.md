# odoo-deploy — push, open MR, drive GitLab CI to green

Date: 2026-09-11
Status: design approved in chat (brainstorming + grilling), pending spec review
Location: `skills/odoo-deploy/` in this repo (symlinked by `link_skills.sh`), plus a
small `odoo setup` change in `odoo-cli`

## Goal

After Odoo implementation work is committed and verified locally, one skill takes
it the rest of the way:

1. Push the branch to GitLab and open (or reuse) the merge request; report the MR URL.
2. Learn the MR pipeline's result from a GitLab webhook delivered through a
   Cloudflare tunnel to an always-on local listener.
3. On failure: fetch the failed jobs' logs, diagnose, fix, verify, push again.
4. Stop when the pipeline is green — notify the user to review and merge — or when an
   escalation rule fires.

## Non-goals

- Deploying to servers. The `deploy` stage only runs on pushes to `dev`/`production`
  (`ACTION=deploy`); this skill only drives the MR pipeline (`ACTION=test`).
- Merging, approving, or enabling auto-merge on the MR — ever (see "No-merge rule").
- Resolving rebase conflicts automatically.
- Any change to the CI template (`infra/cicd-pipeline-template`).
- Team-wide use. One user, one hook, one tunnel hostname. Other developers need an
  Owner/Maintainer to create their own hook and are out of scope.
- A polling fallback for pipeline status (see "Rejected alternatives").
- Running inside the `claude-code` Docker image (see Prerequisites).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Pipeline-result source | GitLab pipeline webhook → Cloudflare named tunnel → local listener; webhook-only, no polling | User choice (grilling Q2); accepted risk below |
| Tunnel | cloudflared named tunnel, remotely managed (`TUNNEL_TOKEN`), hostname on `vdx.vn` | Stable URL → hook set once; vdx.vn DNS is already on Cloudflare |
| Hook | One persistent project hook on the upstream project, pipeline events only, secret token; created/updated by idempotent `gitlab_ci.py setup` | Per-run hooks leak (6 stale quick-tunnel hooks already exist on `sungroup/sca`) |
| Local service | Docker Compose project `skills/odoo-deploy/docker/` (`cloudflared` + `listener`), `restart: unless-stopped` | Starts at OS boot via the enabled Docker daemon; events are never dropped while the machine is on |
| Event store | Listener writes one file per event into the bind-mounted `docker/events/`; `wait` reads that directory | No GitLab polling; survives a crashed `wait` |
| Status authority | `wait` does one GET of the MR's `head_pipeline` at start and one GET of the pipeline on a final-status event | Resume after compaction; out-of-order delivery; stale status after a retry |
| GitLab auth | Stdlib `urllib`; token from `~/.gitlab` for the host, else `git credential fill`; `Authorization: Bearer` | Works with no setup wherever HTTPS `git push` works (glab is the credential helper today) |
| Lint findings | Run CI's own ruff locally (pinned version, template config, `IGNORE_LINTERS`), in preflight and after a CI ruff failure | CI writes findings to `ruff-output`, which is not an artifact; the trace has none |
| Repo discovery | `odoo setup` (odoo-cli) discovers `git_root` + `gitlab_url` into `config/project.json` | The Claude workspace (`sca/`) is not the git repo (`sca/addons`) |
| Trigger | Agent offers odoo-deploy after verification passes; asks once. "Yes" authorizes the first push, every fix commit, and every fix-push of the loop | `git-workflow.md` forbids unrequested pushes |
| Implementation commits | The skill never commits the user's implementation; a dirty tracked tree stops preflight | Which in-progress edits belong in the branch is the user's call |
| Git layout | Push to `origin` (fork); cross-project MR `origin/<branch>` → `upstream/dev`; `--target` overrides | Matches `git-workflow.md`; `dev` is the branch the sun-sca pipeline deploys from |
| Loop limits | Max 3 fix-pushes; escalate earlier on the rules in "Escalation" | Bounds unattended churn |
| End of loop | Final report + Claude Code push notification + Telegram (required) — on green and on escalation | The loop runs unattended; the user may be away |

Accepted risk (webhook-only): GitLab does not queue or re-send a delivery that fails
(machine off, tunnel down). `wait` then ends with exit 3 and the loop escalates;
re-running `/odoo-deploy` recovers the result through `wait`'s initial GET.

### Rejected alternatives

- **Polling the GitLab API** (the original design). Latency ≤ 30 s on a ~10 min
  pipeline and ~20 GETs per pipeline, no inbound access needed. Rejected by the user
  in favour of webhook-only.
- **Webhook + polling fallback.** Keeps all of polling and adds the tunnel on top.
- **`glab` CLI for every request.** Hard dependency; tests mock `subprocess`.
- **cloudflared quick tunnel / ngrok.** Quick-tunnel URLs change per run (hook churn);
  user prefers a company hostname over an ngrok domain.
- **Ephemeral per-run hooks.** Leak on crash/Ctrl-C/compaction.
- **`ruff-output` as a CI artifact.** Needs a template change (non-goal).
- **Baseline comparison against the latest `dev` pipeline.** `dev` push pipelines
  run the same gates and are normally green; rules 3, 4, 6 cover the rest.
- **`odoo setup --merge`.** Existing projects re-run `odoo setup --force`.

## Environment facts (verified 2026-09-11)

GitLab `gitlab.vdx.vn` 18.8.2-ee:
- Fork MR pipelines (`truong/sca` id 90 → `sungroup/sca` id 21) run in the
  **upstream** project; the fork has no CI config. The single-MR API's
  `head_pipeline` includes `id`, `project_id`, `sha`, `status`.
- The upstream project's `ci_config_path` is
  `pipelines/sun-sca.yml@infra/cicd-pipeline-template:sca`.
- Hooks expose `alert_status`/`disabled_until`; hooks to dead URLs stay
  `executable` for 11+ days — failing hooks are not auto-disabled on this instance.
- The user is Owner (access level 50) on `sungroup/sca`.
- Job traces prefix every line with `<ISO-timestamp>Z <NN><O|E>[+] `; artifact lists
  include a `trace` entry for every job.
- `vdx.vn` nameservers are Cloudflare (`nova`/`rory.ns.cloudflare.com`).

CI (`pipelines/sun-sca.yml`, `templates/odoo-cicd.yml`, `config/docker/Dockerfile.cicd-runner`):
- `merge_request_event` pipelines run with `ACTION=test`: `ruff` (quality),
  `parallel-odoo-pytest` (required, artifact `parallel-odoo-test.log`),
  `guard-i18n-source`. `ENABLE_PYLINT` is `false`.
- `unit-test` and `security-scan` are `when: manual`, `allow_failure: true` — they do
  not block, so a pipeline without them finishes `success`.
- `ruff` runs `ruff==0.15.20` over all of `$ODOO_ADDONS_PATH`, with the template's
  `config/linters/ruff/ruff.toml` whose `extend-exclude` line is rewritten from
  `IGNORE_LINTERS` (`scripts/utils.sh` `get_ignore_file_command_ruff`), and writes
  findings to `--output-file ruff-output` — not to the trace, not an artifact.
- `parallel-odoo-pytest` runs **all** custom addons (minus `IGNORE_TEST`); failures
  appear in the trace as `FAILED mnt/custom-addons/<module>/<path>::<Class>::<test>`.
- `dev` push pipelines run the same `ruff` + `parallel-odoo-pytest`
  (`ACTION == test || deploy`); the last 8 were `success`.
- Final pipeline statuses: `success`, `failed`, `canceled`, `skipped`.

Local machine: `~/.gitlab` empty, `GITLAB_TOKEN` unset, `glab` 1.116 logged in (keyring)
and configured as git's credential helper for `https://gitlab.vdx.vn`; Docker 29.1 +
Compose v2, `docker.service` enabled at boot, user in `docker` group; `uvx` available.

## Files

New in this repo:

```
skills/odoo-deploy/
  SKILL.md                  # trigger, setup gate, preflight, loop, escalation
  README.md                 # one-time setup guide; check-setup points into it
  scripts/gitlab_ci.py      # stdlib GitLab + git + lint + notify helper
  docker/compose.yml        # cloudflared + listener, restart: unless-stopped
  docker/listener.py        # stdlib webhook receiver
  docker/.env.example       # TUNNEL_TOKEN=, HOOK_HOSTNAME= (+ keys setup fills)
  tests/test_gitlab_ci.py   # pytest
  tests/test_listener.py    # pytest
```

Edited in this repo (one bullet/row/line each):

- `.gitignore` — add `skills/odoo-deploy/docker/events/` (`.env` is already ignored).
- `skills/odoo/playbooks/git-workflow.md` — replace the "Push + open the MR" bullet
  (which describes a script that does not exist) with: offer odoo-deploy, ask once.
- `skills/odoo/SKILL.md` — add `odoo-deploy` to the process-playbook line.
- `claude-code/CLAUDE.odoo.md` — add a dispatch-table row.

Edited in `odoo-cli` (separate repo, separate commit):

- `src/odoo_cli/setup_discovery.py` — discover `git_root` and `gitlab_url`.
- `tests/test_setup_discovery.py` — cases below.
- `config/project.json.example`, `README.md` — document both fields.

`load_gitlab_config` and the git-remote URL parser are copied (~20 lines) from
`skills/odoo-wlc/scripts/weblate_api.py`, not imported: each skill is symlinked
independently, so a cross-skill import breaks when the other skill is absent.
`config/project.json` is read by walking up from the current directory (same rule as
odoo-cli's `paths._detect_root`, a few lines) — no odoo-cli import.

## Configuration

`config/project.json` (workspace, written by `odoo setup`; already holds `addons_dir`):

| Key | Source | sca value |
|---|---|---|
| `git_root` | `git rev-parse --show-toplevel` of `addons_dir` | `/home/xmars/dev/vdx-vn/sca/addons` |
| `gitlab_url` | scheme + host of the `upstream` remote (else `origin`); SSH remotes map to `https://<host>` | `https://gitlab.vdx.vn` |
| `telegram_channel`, `telegram_token` | existing `odoo setup --setup-telegram` | — (must be added) |

GitLab project paths (`sungroup/sca`, `truong/sca`) are read from the `upstream` /
`origin` remotes at runtime; git config stays the single source of truth.

`skills/odoo-deploy/docker/.env` (chmod 600, gitignored):

| Key | Set by |
|---|---|
| `TUNNEL_TOKEN`, `HOOK_HOSTNAME` | user, from the Cloudflare Zero Trust dashboard (README) |
| `WEBHOOK_SECRET` | `setup`, if absent (`secrets.token_urlsafe(32)`) |
| `FORK_PROJECT_ID` | `setup`, if absent (GET of the `origin` project) |
| `LISTENER_UID`, `LISTENER_GID` | `setup`, if absent (`os.getuid()`/`os.getgid()`) |

`setup` only adds missing keys; it never changes a present value.

GitLab token: `~/.gitlab` `[gitlab]` entry for `gitlab_url`, else
`git credential fill` with `protocol=https`, `host=<host>`, `GIT_TERMINAL_PROMPT=0`.
Sent as `Authorization: Bearer <token>` (accepted for PATs and OAuth tokens).
Tokens and secrets are never printed.

## Docker service: `docker/compose.yml`

- `cloudflared`: pinned `cloudflare/cloudflared` release tag,
  `tunnel --no-autoupdate run`, `TUNNEL_TOKEN` from `.env`. The tunnel's public
  hostname (`HOOK_HOSTNAME`) routes to `http://listener:8080` — configured in the
  Cloudflare dashboard.
- `listener`: `python:3.12-slim`, `user: "${LISTENER_UID}:${LISTENER_GID}"`,
  `listener.py` mounted read-only, `./events` mounted at `/events`. No `ports:` — it
  is reachable only through the tunnel.
- Both `restart: unless-stopped`.

`listener.py` (stdlib `http.server`):
- Only `POST /hook`; everything else → 404. Body over 5 MB → 413.
- `X-Gitlab-Token` compared to `WEBHOOK_SECRET` with `hmac.compare_digest`; mismatch
  or missing → 401.
- Every authenticated delivery rewrites `/events/.last_delivery` (used by
  `check-setup`), then:
  - `object_kind == "pipeline"`, `merge_request` present, and
    `merge_request.source_project_id == FORK_PROJECT_ID` → write the raw payload to
    `/events/<project.id>/<object_attributes.id>/<received_ns>.json` atomically
    (temp file + rename);
  - anything else → discarded.
- Authenticated requests always get 200.

## Script: `scripts/gitlab_ci.py`

Stdlib only. Every command prints exactly one JSON line on stdout. HTTP requests send
a non-default `User-Agent`. Paths: `git_root`, `gitlab_url`, `addons_dir`, Telegram
fields from `config/project.json`; the events dir is `docker/events/` resolved from
the script's real path (works through the `~/.claude/skills` symlink).

HTTP retry policy: up to 3 attempts with 2 s / 5 s backoff on connection/DNS errors,
timeouts, HTTP 429 and 5xx. Other 4xx fail at once. A POST is retried only when no
response arrived (a lost reply never creates a duplicate MR or a double retry).

### `setup`

Idempotent one-time setup (run by the user per README, or by the agent only when the
user asks):
1. `docker/.env` must have `TUNNEL_TOKEN` and `HOOK_HOSTNAME`, else exit 11.
2. Fill missing `.env` keys (table above); chmod 600; create `events/`.
3. `docker compose -f docker/compose.yml up -d`.
4. On the upstream project, find the hook whose URL is `https://$HOOK_HOSTNAME/hook`;
   create it, or PUT it: `pipeline_events: true`, all other events false,
   `token: WEBHOOK_SECRET`, `enable_ssl_verification: true`.
5. Run `check-setup`.

Output: `{"hook_id", "hook": "created"|"updated", "env_added": [...], "check": {...}}`.

### `check-setup`

Run at the start of every skill invocation. Checks (each independent):

| id | Check |
|---|---|
| a | `config/project.json` found with `git_root`, `gitlab_url`; `origin` + `upstream` remotes exist; `upstream` host == `gitlab_url` host |
| b | a token resolves and `GET /user` succeeds |
| c | `docker/.env` has `TUNNEL_TOKEN`, `HOOK_HOSTNAME`, `WEBHOOK_SECRET`, `FORK_PROJECT_ID`, `LISTENER_UID`, `LISTENER_GID` |
| d | `docker compose ps` shows `cloudflared` and `listener` running |
| e | the upstream project has exactly one hook with URL `https://$HOOK_HOSTNAME/hook`, `pipeline_events: true`, `alert_status: executable` |
| f | `uvx` on PATH |
| g | `telegram_channel`, `telegram_token` in `config/project.json`; Telegram `getMe` succeeds |
| h | delivery test: `POST /projects/<upstream>/hooks/<id>/test/pipeline_events`, then `events/.last_delivery` changes within 15 s |

`h` runs only when a–e pass. Output:
`{"ok", "checks": [{"id", "ok", "detail", "fix"}]}` — `fix` names the README section
or command (e.g. "run `odoo setup --force --setup-telegram`"). Any failure → exit 11.

### `lint [--target dev]`

Reproduces the CI `ruff` job locally:
1. Parse the upstream project's `ci_config_path` (`<file>@<project>:<ref>`); read
   `<file>` (`IGNORE_LINTERS`, `ENABLE_RUFF` — top-level `variables:` lines),
   `config/docker/Dockerfile.cicd-runner` (`ruff==<version>`), and
   `config/linters/ruff/ruff.toml` from `<project>` at `<ref>` via the API. Any
   value missing or unparsable → exit 10 (fail closed). `ENABLE_RUFF` not `"true"` →
   `{"skipped": true}`, exit 0.
2. Write the ruff config to a temp file with the `^extend-exclude.*` line replaced
   exactly as `get_ignore_file_command_ruff` does.
3. `uvx ruff@<version> check --config <tmp> --output-format json <addons_dir>`.

Output: `{"ruff_version", "findings": [{"file", "line", "rule", "message", "in_branch"}]}`;
`in_branch` = file is in `git diff --name-only upstream/<target>...HEAD`.
Exit 0 no findings, 1 findings.

### `push [--target dev] [--title TITLE] [--no-rebase]`

Refuses (exit 10) when:
- tracked files have staged or unstaged changes (untracked files are ignored — the
  script never runs `git add`);
- the current branch is `dev`, `main`, `master`, `production`, or equals `--target`.

Default (first push):
1. `git fetch upstream <target>`
2. `git rebase upstream/<target>` — on conflict: `git rebase --abort`, exit 4, JSON
   lists the conflicting files.
3. If `origin/<branch>` already equals `HEAD` → no push (`pushed: false`). Else take
   `since` = `time.time_ns()`, then `git push --force-with-lease origin HEAD:<branch>`
   — rejected → exit 5.

`--no-rebase` (fix iterations and resumes): skip 1–2; step 3 with a plain
`git push origin HEAD:<branch>` (fast-forward).

Then find the open MR on the upstream project with `source_branch=<branch>`,
`target_branch=<target>`, `source_project_id=<fork id>`. None → create it with
`POST /projects/<fork>/merge_requests` and `target_project_id=<upstream id>`, no
auto-merge flags. Title: `--title`, else the subject of the oldest commit in
`upstream/<target>..HEAD`. Description: bullet list of those commit subjects. An
existing MR is not edited.

Output: `{"mr_url", "mr_iid", "sha", "pushed", "since"}` (`since` only when `pushed`).

### `wait --mr IID --sha SHA [--since NS] [--timeout 120]`

A final status "counts" when the status is final and, if `--since` is given, the
pipeline's `finished_at` ≥ `since`.

1. `GET /projects/<upstream>/merge_requests/<iid>` → `head_pipeline`. `sha == SHA` and
   the status counts → output it. `sha == SHA` but not counting → a pipeline exists.
2. Otherwise scan `events/` every 5 s (local disk only) for event files with
   `received_ns ≥ since`, `merge_request.iid == IID`, `object_attributes.sha == SHA`.
   Any such event → a pipeline exists. A final status in an event →
   `GET /projects/<project_id>/pipelines/<id>`; if its status counts → output it,
   else keep scanning.
3. No pipeline for `SHA` within 10 min → exit 3 (`reason: "no_pipeline"`);
   `--timeout` minutes elapsed → exit 3 (`reason: "timeout"`).

Output: `{"pipeline_id", "project_id", "status", "web_url", "reason"}`.

### `fetch-logs --project ID --pipeline ID --out DIR`

For each job of the pipeline with status `failed` and `allow_failure: false`:
- trace → `DIR/<job-name>.log`, ANSI escape codes and the per-line timestamp prefix
  stripped;
- `archive` artifact (if any) → unzipped into `DIR/<job-name>/` (paths escaping `DIR`
  rejected).

Output: `{"jobs": [{"job", "stage", "failure_reason", "trace", "artifacts"}]}`
(`artifacts` is `null` when the job has no `archive`).

### `retry-job --project ID --job ID`

Take `since`, then `POST /projects/<id>/jobs/<job>/retry`.
Output: `{"job_id", "pipeline_id", "since"}` (the new job). The next `wait --since`
ignores the pipeline's earlier final status.

### `notify --text TEXT`

Telegram `sendMessage` to `telegram_channel`. Output `{"telegram": "sent"}` or
`{"telegram": "failed: <reason>"}`; exit 0 either way — a failed send never fails the
loop. The token is never printed.

### `clean --mr IID`

Delete every `events/<project>/<pipeline>/` directory whose events carry
`merge_request.iid == IID`. Output `{"removed": [<pipeline ids>]}`.

### Exit codes

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

## Skill flow: `SKILL.md`

Frontmatter description targets the moment after local verification succeeds, so the
agent offers the skill then; it is also invocable as `/odoo-deploy [--target BRANCH]`.

Working directory: the Odoo workspace (where `config/project.json` lives); git runs in
`git_root`. Scratch: `<workspace>/tmp/odoo-deploy/<branch>/` (`/` in the branch name
→ `-`; per `CLAUDE.odoo.md` "File locations"). Keyed by branch so a re-run finds it
before the MR IID is known.

1. **Offer.** Implementation committed and verified → ask once: "Push to GitLab and
   drive CI to green?" No → stop. Yes → the whole loop below is authorized.
2. **Setup gate.** `gitlab_ci.py check-setup`. Exit 11 → stop; relay the failed
   checks and their README fixes. Never start the loop on an incomplete setup.
3. **Preflight.**
   - Dirty tracked files → stop: "commit or stash first (git-workflow.md)".
   - Local verification evidence from this session (the project's rules:
     `odoo verify`, tests via `agy`/`odoo runtime-test` over the in-scope modules). No
     evidence → run verification first; never push unverified work.
   - `gitlab_ci.py lint`. Findings with `in_branch: false` → escalate (rule 3) before
     any push. Findings with `in_branch: true` → fix, re-verify, commit
     `[FIX] <module>: ruff` with explicit paths (not a fix-push; no cap consumed).
4. **Push.** `gitlab_ci.py push`, or `push --no-rebase` when `loop.md` exists (resume).
   Print the MR URL to the user immediately.
5. **Wait.** `gitlab_ci.py wait --mr IID --sha SHA [--since NS]` (`--since` only when
   the push/retry output has one) as a background Bash command; the session is
   re-invoked when it exits.
6. **Green (exit 0).** Final report: MR URL, pipeline URL, fix commits (if any),
   iterations used, and "review and merge it yourself". Send the push notification
   and `gitlab_ci.py notify` with `MR !<iid> green — review and merge it yourself:
   <url>`. Then `gitlab_ci.py clean --mr IID` and delete the scratch dir.
7. **Red (exit 1).**
   1. `fetch-logs` into `<scratch>/pipeline-<id>/`. A failed `ruff` job → also
      `gitlab_ci.py lint` (the trace has no findings).
   2. Check escalation rules (below) against the manifest, traces, and lint output.
   3. Triage with odoo-debug's `test-failure-log-triage` playbook: one failure per
      traceback, each classified (app bug / wrong test / environment). Lint: one
      finding per file + rule.
   4. Reproduce locally (re-run the failing tests / `lint`), fix through the owning
      skill (`odoo-model`, `odoo-view`, ...), re-verify per step 3 (including `lint`).
   5. Commit `[FIX] <module>: <desc>` with explicit paths.
   6. `gitlab_ci.py push --no-rebase`, then back to step 5.
8. **Loop log.** Every iteration appends to `<scratch>/loop.md`: iteration number,
   pipeline id/URL, failure signatures, fix commit SHA. The cap, the repeat check, and
   resume detection read this file, so they survive conversation compaction.

Fix iterations never rebase: the CI delta between iterations is caused by our fix,
not by new upstream commits.

### No-merge rule

The agent never merges, approves, or enables auto-merge
(`merge_when_pipeline_succeeds`) on the MR — not through `gitlab_ci.py`, `glab`,
`curl`, or the web UI. `gitlab_ci.py` has no merge or approve command. Merging is the
user's decision after reviewing the green MR.

### Failure signatures

Used by the "same failure repeats" rule:
- pytest failure: `<job>::<test node id>`
- lint finding: `<job>::<file>::<rule code>` (line numbers excluded — they shift)
- anything else: `<job>::<first error line of the trace>`

### Scope

In-scope modules = addons touched by `git diff --name-only upstream/<target>...HEAD`
plus their transitive reverse dependencies (method in `CLAUDE.odoo.md`, "Determine the
validation scope"). A pytest failure's module is the path segment after
`custom-addons/` in its node id.

## Escalation

When any rule fires: stop the loop, keep the scratch dir and this MR's events, report
MR URL, pipeline URL, the rule that fired, and the evidence (file paths into the saved
logs); send the push notification and `gitlab_ci.py notify` with
`MR !<iid> stopped (rule <n>) — needs you: <url>`; then ask the user how to proceed.

1. 3 fix-pushes already made.
2. Infra failure — `failure_reason` is not `script_failure`, or the trace shows a
   Vault, docker pull, network, or disk-space error: `retry-job` once per job; the
   same job failing on infra again → escalate.
3. Failure outside scope: a module not in the in-scope set, or a lint finding in a
   file the branch did not touch (pre-existing).
4. A failure signature already recorded in `loop.md` for an earlier iteration.
5. The fix would change a test assertion or expected value, a migration script,
   ACL/record rules, or `.po`/`.pot` files.
6. The failure cannot be reproduced locally and the log does not pin down the cause.
7. `push` exits 4 or 5; `wait` exits 2 or 3; any command exits 10.

`check-setup` exit 11 is not an escalation: the loop never started (flow step 2).

## `README.md` (setup guide)

Sections, each a `check-setup` `fix` target:
1. **Prerequisites** — Owner/Maintainer on the upstream project; Docker enabled at
   boot and the user in the `docker` group; `uvx`; Cloudflare Zero Trust access to
   the `vdx.vn` account.
2. **Cloudflare tunnel** — create a remotely managed tunnel; add public hostname
   `<name>.vdx.vn` → `http://listener:8080`; copy `.env.example` to `.env`; set
   `TUNNEL_TOKEN`, `HOOK_HOSTNAME`.
3. **Project config** — `odoo setup --force --setup-telegram` in the workspace
   (adds `git_root`, `gitlab_url`, Telegram fields; `--force` rewrites the file).
4. **GitLab token** — nothing to do when HTTPS `git push` works; otherwise a
   `~/.gitlab` `[gitlab]` entry with an `api`-scope token.
5. **Run setup** — `python3 skills/odoo-deploy/scripts/gitlab_ci.py setup` from the
   workspace; expect `check.ok: true`.
6. **Troubleshooting** — one entry per `check-setup` id (a–h).

## Prerequisites

- `git push origin` works with the machine's existing git auth.
- Everything in README section 1.
- In the `claude-code` Docker container none of this is present by default; making it
  available is the user's decision and is not changed by this work.

## Testing

`skills/odoo-deploy/tests/test_gitlab_ci.py`, pytest, same style as
`skills/odoo-wlc/tests/test_weblate_api.py` (`urllib.request.urlopen` monkeypatched,
`subprocess` mocked for `git credential`, `docker`, `uvx`; time injected, no real
sleeping):

- config: `project.json` walk-up; token from `~/.gitlab` by host, else
  `git credential fill`; neither → exit 10; `Authorization: Bearer` header.
- retry policy: DNS/URLError then success; 5xx/429 retried; 4xx not retried; POST not
  retried after a response.
- remote URL parsing: SSH and HTTPS forms.
- MR: reuse an open MR (matching `source_project_id`); create with `target_project_id`
  and no auto-merge flags when none; default title from the oldest commit.
- `push` against temporary bare `origin`/`upstream` repos: refuses dirty tracked tree;
  ignores untracked files; refuses protected branches; rebase conflict → aborted,
  exit 4; `--no-rebase` does a plain fast-forward push; non-fast-forward → exit 5;
  remote already at `HEAD` → `pushed: false`, no `since`.
- `wait`: initial GET returns a counting final status at once; a final status with
  `finished_at < since` is ignored; events for other IIDs/SHAs or older than `since`
  ignored; confirmation GET not final → keeps scanning; exit 0/1/2 per status; exit 3
  `no_pipeline` and `timeout`.
- `fetch-logs`: skips `allow_failure` and non-failed jobs; ANSI and timestamp prefix
  stripped; only `archive` artifacts unzipped; zip-slip rejected; manifest shape.
- `lint`: `ci_config_path` parsing; version and variable parsing; unparsable → exit 10;
  `extend-exclude` rewrite identical to `get_ignore_file_command_ruff` output;
  `in_branch` flag; `ENABLE_RUFF` false → skipped.
- `retry-job`: output carries `since` taken before the POST.
- `setup`: adds only missing `.env` keys; creates vs. updates the hook; compose
  invoked; ends with `check-setup`.
- `check-setup`: each check fails independently with its `fix`; `h` skipped when a–e
  fail; `.last_delivery` change detected; exit 11.
- `notify`: `sendMessage` payload; failure → exit 0 with reason; token absent from
  output.
- `clean`: removes only directories whose events match the IID.

`skills/odoo-deploy/tests/test_listener.py` — real server on an ephemeral port, temp
events dir: wrong/missing secret → 401; other method/path → 404; oversize → 413;
authenticated delivery rewrites `.last_delivery`; fork MR pipeline event stored at
`<project>/<pipeline>/<ns>.json`; other source project / no MR / non-pipeline
discarded with 200.

`odoo-cli` `tests/test_setup_discovery.py`: `git_root` from `addons_dir`;
`gitlab_url` from SSH and HTTPS `upstream`, `origin` fallback; non-git tree → both
reported missing.

Acceptance (run by the user on a throwaway branch of `sca/addons`, pushes to
gitlab.vdx.vn; the user closes the MR afterwards):
- **(a) Setup.** `setup` then `check-setup` pass, including delivery test `h`.
- **(b) CI-only app bug.** Add `if os.environ.get("CI"): raise UserError("acceptance")`
  to a method covered by an existing in-scope test. Pass = MR URL printed; first
  pipeline red; trace fetched; a `[FIX]` commit removes the line; second pipeline
  green via the webhook; `loop.md` shows one iteration; this MR's events removed;
  Telegram + push notification received; MR not merged.
- **(c) Ruff violation.** Caught by preflight `lint`; no pipeline spent.

## Assumptions to verify during implementation

- Pipeline webhook payloads for MR pipelines on 18.8 carry `merge_request.iid` and
  `merge_request.source_project_id`, and `object_attributes.sha`/`status`.
- `POST /projects/:id/hooks/:hook_id/test/pipeline_events` is available and delivers
  through the real hook URL.
- `head_pipeline` and `GET /pipelines/:id` include `finished_at`, reset while a
  retried pipeline runs.
- The GitLab server can reach Cloudflare's edge over HTTPS (proved by check `h`).
- The user's Cloudflare login can create tunnels and public hostnames in the `vdx.vn`
  zone.
