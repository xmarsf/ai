---
name: odoo-test
description: >-
  Use when authoring or running Odoo tests: writing test classes, cases, or JS
  tours; selecting and placing cases in a module's tests/ layout; or executing
  suites with `odoo runtime-test`. Triggers: a request for tests, coverage
  work, TDD, or a green-before-merge check — before any test file is written
  or a suite is run for a verdict.
---

# odoo-test — author and run Odoo tests

Test authoring and execution for Odoo addons. Triaging an already-produced
failing log belongs to **odoo-debug** (`test-failure-log-triage`); the Python
or XML changes under test belong to **odoo-model** / **odoo-view**.

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

Tests run against version-specific behavior — before asserting "this test
fails/passes on this version", check `odoo compat get <id>` or
`odoo compat list --kind python-api`.

## Playbook routing (lazy-loaded — read only the one routed, never bulk-read)

| Playbook | Read it when |
|---|---|
| [write-odoo-tests](playbooks/write-odoo-tests.md) | main entry point — type table, order of operations |
| [test-case-selection](playbooks/test-case-selection.md) | mandatory before ANY test write — build the case table |
| [test-module-structure](playbooks/test-module-structure.md) | tests/ layout, Common classes, `setUpClass`/`tearDownClass`, tags |
| [test-cross-module](playbooks/test-cross-module.md) | behavior spans addons — owner module, shared fixtures |
| [tour-test-authoring](playbooks/tour-test-authoring.md) | JS tour + `HttpCase.start_tour` authoring |
| [patch-documented-test-gap](playbooks/patch-documented-test-gap.md) | a coverage doc marks a method "not covered by any test" |
| [reference/test-anti-patterns](playbooks/reference/test-anti-patterns.md) | anti-pattern checklist when mocks/heavy fixtures tempt |

## Hard rules

- **`test-case-selection` before any test write** — no improvised case lists,
  no "obvious cases" from memory; a feature playbook's sample cases are inputs
  into selection, not a substitute.
- Run tests **only** via `odoo runtime-test --module <m> [--tests <path>]
  [--output <dir>/runtime-test.json]` — never a hand-rolled pytest-odoo
  invocation. `--http` for HttpCase/tour tests; `--init update` (or `odoo
  module update` first) when the test needs new schema.
- Confirm red for the right reason (missing feature, not typo/setup) before
  implementing; the runner's raw summary is authoritative over your arithmetic.
- Schema-only changes (declarative UI, field defs) follow the module-update
  path — no TDD unless behavior changes.
- A pasted multi-failure log routes to **odoo-debug**
  (`test-failure-log-triage`); this skill writes and runs, that one triages.
