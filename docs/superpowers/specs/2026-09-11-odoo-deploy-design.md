# odoo-deploy — push, open MR, drive GitLab CI to green

Date: 2026-09-11
Status: design approved in chat, pending spec review
Location: `skills/odoo-deploy/` in this repo (symlinked by `link_skills.sh`)

## Goal

After Odoo implementation work is committed and verified locally, one skill takes
it the rest of the way:

1. Push the branch to GitLab and open (or reuse) the merge request; report the MR URL.
2. Wait for the MR pipeline.
3. On failure: fetch the failed jobs' logs locally, diagnose, fix, verify, push again.
4. Stop when the pipeline is green — or when an escalation rule fires.

## Non-goals

- Deploying to servers. The `deploy` stage only runs on pushes to `dev`/`production`
  (`ACTION=deploy`); this skill only drives the MR pipeline (`ACTION=test`).
- Merging the MR.
- Resolving rebase conflicts automatically.
- Any change to the CI template (`infra/cicd-pipeline-template`).
- Running inside the `claude-code` Docker image without extra setup (see Prerequisites).

## Decisions (from brainstorming)

| Topic | Decision | Why |
|---|---|---|
| Log source | Agent polls GitLab API; downloads failed job traces + artifacts itself | A runner pushing files to a dev machine needs inbound access to it; polling needs nothing CI-side |
| Trigger | Agent offers odoo-deploy after verification passes; asks once. "Yes" authorizes the first push and every fix-push of the loop | `git-workflow.md` forbids unrequested pushes; one explicit confirmation keeps the human gate without per-iteration prompts |
| Git layout | Push to `origin` (fork); cross-project MR `origin/<branch>` → `upstream/dev`; target overridable with `--target` | Matches `git-workflow.md`; `dev` is the branch the sun-sca pipeline deploys from |
| Loop limits | Max 3 fix-pushes; escalate earlier on the rules in "Escalation" | Bounds unattended churn |
| Implementation | Stdlib Python script + background wait (Approach A) | `glab` is not authenticated to gitlab.vdx.vn and not in the Docker image; `~/.gitlab` + stdlib already works in `odoo-wlc` |

Rejected: `glab` CLI (auth/install per machine, awkward fork-MR pipeline lookup);
bash + curl + jq (extra dependency, brittle JSON parsing, harder to test).

## CI facts this design relies on

From `cicd-pipeline-template/pipelines/sun-sca.yml` and `templates/odoo-cicd.yml`:

- `merge_request_event` pipelines run with `ACTION=test`: `pylint`, `ruff` (quality),
  `parallel-odoo-pytest` (required, artifact `parallel-odoo-test.log`).
- `unit-test` and `security-scan` are `when: manual`, `allow_failure: true` — they do
  not block, so a pipeline without them finishes `success`.
- Final pipeline statuses: `success`, `failed`, `canceled`, `skipped`.

## Files

New:

```
skills/odoo-deploy/
  SKILL.md                 # trigger, preflight, loop, escalation
  scripts/gitlab_ci.py     # stdlib GitLab + git helper
  tests/test_gitlab_ci.py  # pytest
```

Edited (one bullet/row each):

- `skills/odoo/playbooks/git-workflow.md` — replace the "Push + open the MR" bullet
  (which describes a script that does not exist) with: offer odoo-deploy, ask once.
- `skills/odoo/SKILL.md` — add `odoo-deploy` to the process-playbook line.
- `claude-code/CLAUDE.odoo.md` — add a dispatch-table row.

`load_gitlab_config` and the git-remote URL parser are copied (~20 lines) from
`skills/odoo-wlc/scripts/weblate_api.py`, not imported: each skill is symlinked
independently, so a cross-skill import breaks when the other skill is absent.

## Script: `scripts/gitlab_ci.py`

Stdlib only. Auth: `~/.gitlab`, `[gitlab]` section, `<host-url> = <token>` — the
host is taken from the remote URL. Every command prints exactly one JSON line on
stdout. Tokens are never printed. HTTP requests send a non-default `User-Agent`.

Project paths come from `git remote get-url origin|upstream` (SSH and HTTPS forms).

### `push [--target dev] [--title TITLE] [--no-rebase]`

Refuses (exit 10) when:
- tracked files have staged or unstaged changes (untracked files are ignored — the
  script never runs `git add`);
- the current branch is `dev`, `main`, `master`, `production`, or equals `--target`.

Default (first push):
1. `git fetch upstream <target>`
2. `git rebase upstream/<target>` — on conflict: `git rebase --abort`, exit 4, JSON
   lists the conflicting files.
3. `git push --force-with-lease origin HEAD:<branch>` — rejected → exit 5.

`--no-rebase` (fix iterations): skip 1–2, plain `git push origin HEAD:<branch>`
(fast-forward); rejected → exit 5.

Then find the open MR on the upstream project with `source_branch=<branch>`,
`target_branch=<target>`, `source_project_id=<fork id>`. None → create it with
`POST /projects/<fork>/merge_requests` and `target_project_id=<upstream id>`.
Title: `--title`, else the subject of the oldest commit in `upstream/<target>..HEAD`.
Description: bullet list of those commit subjects. An existing MR is not edited.

Output: `{"mr_url", "mr_iid", "sha"}` (`sha` = pushed `HEAD`).

### `wait --mr IID --sha SHA [--timeout 120]`

Every 30 s: `GET /projects/<upstream>/merge_requests/<iid>`, read `head_pipeline`.
Keep polling until `head_pipeline.sha == SHA` and its status is final.

Output: `{"pipeline_id", "project_id", "status", "web_url", "reason"}`.
`project_id` is where the pipeline ran (for fork MRs this may be the fork).

### `fetch-logs --project ID --pipeline ID --out DIR`

For each job of the pipeline with status `failed` and `allow_failure: false`:
- trace → `DIR/<job-name>.log`, ANSI escape codes stripped;
- artifacts (if any) → unzipped into `DIR/<job-name>/`.

Output: `{"jobs": [{"job", "stage", "failure_reason", "trace", "artifacts"}]}`
(`artifacts` is `null` when the job has none).

### `retry-job --project ID --job ID`

`POST /projects/<id>/jobs/<job>/retry`, then poll the job's pipeline (≤ 60 s) until
its status is no longer final, so the next `wait` does not read the stale `failed`.
Output: `{"job_id", "pipeline_id"}` (the new job).

### Exit codes

| Code | Meaning |
|---|---|
| 0 | ok / pipeline `success` |
| 1 | pipeline `failed` |
| 2 | pipeline `canceled` or `skipped` |
| 3 | no pipeline for `SHA` within 10 min, or `--timeout` minutes elapsed (`reason` says which) |
| 4 | rebase conflict (rebase aborted) |
| 5 | push rejected |
| 10 | usage, config, auth, or API error (message on stderr) |

## Skill flow: `SKILL.md`

Frontmatter description targets the moment after local verification succeeds, so the
agent offers the skill then; it is also invocable as `/odoo-deploy [--target BRANCH]`.

Working directory: the Odoo project root. Scratch: `<project>/tmp/odoo-deploy/mr-<iid>/`
(per `CLAUDE.odoo.md` "File locations").

1. **Offer.** Implementation committed and verified → ask once: "Push to GitLab and
   drive CI to green?" No → stop. Yes → the whole loop below is authorized.
2. **Preflight.** `origin` and `upstream` remotes exist; `~/.gitlab` has a token for
   the host; local verification evidence exists from this session (the project's
   rules: `odoo verify`, tests via `agy`/`odoo runtime-test` over changed modules plus
   transitive dependents). No evidence → run verification first; never push
   unverified work. Uncommitted work → commit it with explicit paths (never
   `git add -A`), commit style `[TYPE] module: desc`.
3. **Push.** `gitlab_ci.py push`. Print the MR URL to the user immediately.
4. **Wait.** `gitlab_ci.py wait` as a background Bash command; the session is
   re-invoked when it exits.
5. **Green (exit 0).** Final report: MR URL, pipeline URL, fix commits (if any),
   iterations used. Delete `tmp/odoo-deploy/mr-<iid>/`.
6. **Red (exit 1).**
   1. `fetch-logs` into `tmp/odoo-deploy/mr-<iid>/pipeline-<id>/`.
   2. Check escalation rules (below) against the manifest and traces.
   3. Triage with odoo-debug's `test-failure-log-triage` playbook: one failure per
      traceback, each classified (app bug / wrong test / environment). Lint jobs:
      one finding per file + rule.
   4. Reproduce locally (re-run the failing tests / linter), fix through the owning
      skill (`odoo-model`, `odoo-view`, ...), re-verify per step 2's rules.
   5. Commit `[FIX] <module>: <desc>` with explicit paths.
   6. `gitlab_ci.py push --no-rebase`, then back to step 4.
7. **Loop log.** Every iteration appends to `tmp/odoo-deploy/mr-<iid>/loop.md`:
   iteration number, pipeline id/URL, failure signatures, fix commit SHA. The cap and
   the repeat check read this file, so they survive conversation compaction.

Fix iterations never rebase: the CI delta between iterations is caused by our fix,
not by new upstream commits.

### Failure signatures

Used by the "same failure repeats" rule:
- pytest failure: `<job>::<test node id>`
- lint finding: `<job>::<file>::<rule code>` (line numbers excluded — they shift)
- anything else: `<job>::<first error line of the trace>`

### Scope

In-scope modules = addons touched by `git diff --name-only upstream/<target>...HEAD`
plus their transitive reverse dependencies (method in `CLAUDE.odoo.md`, "Determine the
validation scope").

## Escalation

When any rule fires: stop the loop, keep `tmp/odoo-deploy/mr-<iid>/`, report MR URL,
pipeline URL, the rule that fired, and the evidence (file paths into the saved logs),
then ask the user how to proceed.

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

## Prerequisites

- `git push origin` works with the machine's existing git auth.
- `~/.gitlab` with a token (`api` scope) for gitlab.vdx.vn.
- In the `claude-code` Docker container both are absent by default; mounting them is
  the user's decision and is not changed by this work.

## Testing

`skills/odoo-deploy/tests/test_gitlab_ci.py`, pytest, same style as
`skills/odoo-wlc/tests/test_weblate_api.py` (`urllib.request.urlopen` monkeypatched):

- config: token picked by remote host; missing file/section/host → exit 10.
- remote URL parsing: SSH and HTTPS forms.
- MR: reuse an open MR (matching `source_project_id`); create with `target_project_id`
  when none; default title from the oldest commit.
- `wait`: ignores `head_pipeline` for other SHAs; exit 0/1/2 per status; exit 3 when
  no pipeline appears (time injected, no real sleeping).
- `fetch-logs`: skips `allow_failure` and non-failed jobs; ANSI stripped; artifacts
  unzipped; manifest shape.
- `retry-job`: returns only after the pipeline leaves a final status.
- `push` against temporary bare `origin`/`upstream` repos: refuses dirty tracked tree;
  ignores untracked files; refuses protected branches; rebase conflict → aborted,
  exit 4; `--no-rebase` does a plain fast-forward push; non-fast-forward → exit 5.

Acceptance (run by the user, pushes to gitlab.vdx.vn): a throwaway branch in an Odoo
project with one deliberate ruff violation. Pass = MR URL printed, ruff failure
fetched and fixed, second pipeline green, `loop.md` shows one iteration.

## Assumptions to verify during implementation

- The single-MR API's `head_pipeline` includes `project_id` and `sha` on gitlab.vdx.vn's
  GitLab version. If not: fall back to `GET /projects/<upstream>/merge_requests/<iid>/pipelines`
  filtered by `sha`, trying the upstream then the fork project for job lookups.
- Fork MR pipelines run somewhere the token can read (fork or upstream project).
