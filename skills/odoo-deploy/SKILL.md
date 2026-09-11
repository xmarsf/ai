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

`wait` exiting 3 with `reason: no_pipeline` or `reason: timeout` — including
when the cause was a dropped webhook (machine off, tunnel down; GitLab does
not re-send a failed delivery) — still fires rule 7. Stop and notify the
user; never silently retry in the background.

Recovery happens on the next user-initiated run: re-running `/odoo-deploy`
on the same branch picks up whatever happened in the meantime through
`wait`'s own initial GET of the MR's `head_pipeline`, which does not depend
on the webhook having arrived at all. That run resumes via step 4's
`--no-rebase` push (a no-op when already up to date), then step 5's `wait`.
