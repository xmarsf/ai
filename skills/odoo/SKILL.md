---
name: odoo
description: >-
  Use when working on Odoo addon code in any project — python models, fields,
  constraints, security, wizards, controllers, automation; XML views, reports,
  assets; tests; migration scripts — or when triaging Odoo failures, running
  odoo-cli checks, porting code between Odoo majors (17/18/19), or answering any
  version-specific Odoo API question. Projects may be community or enterprise.
  Translation and Weblate work routes to odoo-wlc instead.
---

# odoo — version-aware Odoo work router

Thin router, not a worker: it resolves which Odoo version and core tree this
project targets, refuses to operate unconfigured, then dispatches to a task
skill for the actual work. Projects here span Odoo 17/18/19; code that is
correct on one major can be removed or silently ignored on another, so every
version-specific claim is checked against the declared core tree, never made
from memory.

## Opening protocol (run in order, before any Odoo work)

Work in the Odoo project the task targets (the repo holding the addons).

1. **Read `config/project.json`** at the project root. Missing → emit the
   refusal line below and stop. Do nothing else — no best-effort guesses.
2. **Read `odoo-version`** (e.g. `"18 community"`). Null or absent → emit the
   refusal line and stop.
3. **Read `odoo_community_path`** (and **`odoo_enterprise_path`** too when the
   edition is enterprise). Null or not a directory → emit the refusal line and
   stop. **No fallback**: never substitute another project's tree, a shared
   `~/dev/odoo/*` checkout, or the addon dir itself for a declared core path.
4. **First line of your reply states the resolution**, so any wrong answer is
   traceable to a wrong tree:
   `Odoo <major> <edition> — core: <odoo_community_path>` (add
   `— enterprise: <odoo_enterprise_path>` when edition is enterprise).
5. **Dispatch** by artifact type (table below). Before asserting ANY
   version-specific fact — an API existing, being deprecated or removed, a view
   tag, a base-class change — run `odoo compat get <id>` (from the project
   root, so it resolves the config) or `odoo compat list`. Never from memory,
   not even for facts you are sure of; see reference/versions.md.

**Refusal line** (steps 1–3, emit verbatim, then stop):
`No resolved Odoo version/core tree for this project. Run 'odoo setup' in the project root, then retry.`
(`odoo setup` writes/refreshes `config/project.json`; preview with `--dry-run`.)

## Dispatch table

| Artifact / task shape | Route to |
| --- | --- |
| Python: models, fields, `_inherit`, constraints, security, wizards, controllers, automation | `odoo-model` |
| XML: views, inheritance, widgets, settings, assets, QWeb reports | `odoo-view` |
| Writing or running tests | `odoo-test` |
| Failing behavior, triage, live/DB inspection | `odoo-debug` |
| Cross-major port, migration scripts | `odoo-upgrade` |
| Translation (.po round-trip, Weblate) | `odoo-wlc` (existing skill — explicitly out of scope here) |

Process playbooks live in this skill, under `playbooks/` — run
[task-evaluation](playbooks/task-evaluation.md) first on any task; then as
triggered: [diagnosis-before-implementation](playbooks/diagnosis-before-implementation.md),
[git-workflow](playbooks/git-workflow.md) (commit; push/MR only when asked),
[pr-review](playbooks/pr-review.md), [session-review](playbooks/session-review.md).

The task skills hold their own playbooks and match the specific one by trigger;
match at skill granularity here. Read playbooks lazily — open one when its
trigger fires, never bulk-read.

## Version facts

reference/versions.md — per-major differences at a glance; every row is a
`odoo compat` matrix id, not an assertion. reference/cli.md — which odoo-cli
command for which job (`verify`, `lint-rules`, `runtime-test`, `compat`, ...).

## Lesson routing (a quirk found during work)

Found behavior that contradicts a version assumption? Locate the proof in the
declared core tree, then `odoo compat add` — it writes the entry as
`status: candidate` and prints the push command; you hand it to the user to
push the branch and open the MR on gitlab.vdx.vn; review promotes it to
`confirmed`. A quirk with no reproducible core proof is not admitted — it stays
a project-local note and is never asserted from memory. Full loop and admission
test: [reference/updating.md](reference/updating.md).
