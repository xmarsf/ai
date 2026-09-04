---
name: odoo-debug
description: >-
  Use when triaging an already-observed Odoo failure: a traceback or failing
  test log, wrong data on a local or live database record, XML
  ParseError/ValidationError/Invalid view output, or probing a running
  instance via XML-RPC. Triggers: "why does this fail", an error dump, a bug
  report against real data — diagnosis before code changes.
---

# odoo-debug — triage failing Odoo output

Diagnosis of output that already exists: shell, logs, live inspection, XML-RPC.
Once the defect is scoped, the fix routes back to the artifact skill that owns
the change (**odoo-model**, **odoo-view**), with tests via **odoo-test**.

## Before anything else

Read `config/project.json` at the project root and follow the five-step opening
protocol in the **odoo** router skill ([../odoo/SKILL.md](../odoo/SKILL.md)): missing/null
`odoo-version`, or null/absent `odoo_community_path` (plus
`odoo_enterprise_path` for the enterprise edition) → stop and tell the user to
run `odoo setup`. **No fallback.** If you reached this skill directly (no
router), still resolve the version first under the same rules, and state
`Odoo <major> <edition> — core: <odoo_community_path>` in your first output
line (add `— enterprise: <odoo_enterprise_path>` when the edition is
enterprise).

Error text is version-dependent — before claiming "this error means the API
was removed", check `odoo compat get <id>` or `odoo compat list`.

Process entry: [diagnosis-before-implementation](../odoo/playbooks/diagnosis-before-implementation.md)
(router playbook) — every triage below starts there.

## Playbook routing (lazy-loaded — read only the one routed, never bulk-read)

| Playbook | Read it when |
|---|---|
| [live-debug](playbooks/live-debug.md) | debug a live/dev Odoo URL directly, credentials via `.env` |
| [local-record-debug](playbooks/local-record-debug.md) | wrong data on a specific local dev-DB record |
| [xml-debug](playbooks/xml-debug.md) | XML load/validation failure (`ParseError`, `Invalid view`, silent no-op) |
| [xmlrpc-live-query](playbooks/xmlrpc-live-query.md) | probe a live/remote instance via XML-RPC/JSON-RPC |
| [test-failure-log-triage](playbooks/test-failure-log-triage.md) | a pasted pytest/Odoo log with multiple failing tests |
| [account-sequence-date-mismatch-triage](playbooks/account-sequence-date-mismatch-triage.md) | posting fails on journal sequence/date conflict |
| [action-button-double-trigger-guard](playbooks/action-button-double-trigger-guard.md) | a state-transition button double-fires |

## Hard rules

- Diagnosis before implementation: gather evidence, classify (app bug / wrong
  test / environment-schema), map to source — then hand the scoped defect to
  the owning skill. Do not patch while still triaging.
- Read-only on live/dev data unless explicitly asked; never mutate a live
  database, never re-enable a cron to "see what happens".
- Never paste account/password/token/cookie/db/host details anywhere — refer to
  the `.env` path and key names instead.
- Never reuse a pasted log's db name; confirm against `config/project.json`
  (the db `odoo runtime-test` uses).
- "Missing table"/"invalid field" at setup → check `ir_module_module.state` vs
  `to_regclass` and run `-u` before assuming a code bug.
