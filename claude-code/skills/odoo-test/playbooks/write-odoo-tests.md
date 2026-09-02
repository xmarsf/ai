# write-odoo-tests

Applies when: a request or another playbook needs Odoo testing work — new/updated
tests, a documented coverage gap, a JS tour, or triage of a pasted pytest/Odoo failure
log. Main testing entry point in the odoo skill's dispatch table; routes special
cases, **case selection**, **placement**, and **type** decisions before any test write.

Entry point: [SKILL.md](../SKILL.md), [the odoo skill](../../odoo/SKILL.md)

## Usage
- used: 6
- last used: 2026-07-19

## Steps

- [ ] **Route before writing:** pasted raw failure log → run playbook
  [test-failure-log-triage](../../odoo-debug/playbooks/test-failure-log-triage.md), stop here. Doc-marked coverage gap → run playbook [patch-documented-test-gap](patch-documented-test-gap.md), stop here. Otherwise continue.
- [ ] **Feature-case inputs before selection (order).** When the parent plan /
  `expand-when` already names a feature playbook that **defines owned cases** for
  this behavior (examples: [add-active-field-archive](../../odoo-model/playbooks/add-active-field-archive.md)
  for archive/soft-delete; field/constraint/wizard children that list create+write
  guards), **expand that playbook first** and treat its sample cases as
  **candidates** for the next step. Do **not** finish case selection, then open
  the feature playbook mid-implement and patch via tdd follow-up — that is process
  rework (extra turns/tokens). Log the feature expansion in the task notes
  (expanded before test-case-selection, or the parent call-site when).
- [ ] **Case selection (mandatory hard gate).** Open and fully execute
  [test-case-selection](test-case-selection.md) (returning) **before any type pick,
  placement, or test file write**. Record in the task notes that selection ran.
  **Forbidden:** improvised case lists, dispatch-prompt-only tables, "obvious cases"
  written from memory, or skipping selection because another playbook already lists
  sample cases — those are inputs *into* selection, not a substitute. Empty table
  after selection → stop TDD (**module-update path**). No tests may be authored
  without this step's finished case table.
- [ ] **Placement** — run playbook [test-module-structure](test-module-structure.md)
  (returning). If the change spans addons, `_inherit`s foreign models, or is glue
  between modules → also run playbook [test-cross-module](test-cross-module.md)
  (returning). Record owner module + Common to extend.
- [ ] **Pick test type(s)** per behavior surface (table below) for each remaining
  case. Prefer the lightest type that can fail for the right reason. Report surface(s);
  anything beyond single-model `TransactionCase` means a heavier test-writing pass
  ([task-evaluation](../../odoo/playbooks/task-evaluation.md)).

| Behavior surface | Test type | knowledge-base note |
|---|---|---|
| `create`/`write`/`unlink`/`copy`, `@api.constrains`, `@api.depends` compute, state-machine method, security/record rule | `TransactionCase`/`BaseCommon`, `tests/test_*.py` | note: Unit Test Odoo |
| UI-triggered onchange chain, or view modifier (invisible/readonly/required) gating a field | `Form` — `from odoo.tests import Form` | note: Form Test |
| Multi-step browser UI flow: wizard, drag-drop, kanban, widget JS | JS tour via `HttpCase.start_tour` | note: Tour Test |
| HTTP controller/endpoint, no UI | `HttpCase` (no tour) | note: Unit Test Odoo (`HttpCase`); source: `odoo/tests/common.py` |

- [ ] **Type need/don't** (minimal assertions at the right seam — not "more things"):

**TransactionCase**: real entrypoint (`create`/`write`/action/constraint/compute/access),
assert business result (not just no-exception), include the branching condition
(state/user/company/context), minimal fixtures (addon Common only if needed),
the Test Isolation rule, run as relevant user for security bugs.
Class-level master-data mutation → snapshot + `tearDownClass` restore (placement:
[test-module-structure](test-module-structure.md)). Don't: Form for pure backend,
full lifecycle when one method is the seam, assert every field, heaviest sibling
fixture when 1–2 records suffice.

**Form**: exercise via `Form(...)` assign/edit, assert UI-facing effect + post-`save()`
persisted values, open the relevant view if modifiers matter, correct edit/create mode.
Don't: tour for plain onchange/modifier, assert only "didn't raise", Form without
onchange/modifier dependency.

**Tour**: real browser/widget needs only; JS tour + `HttpCase.start_tour`;
`web.assets_tests`; tags per convention; assert DB outcome after tour. Don't: tour when
TransactionCase/Form covers it; bootstrap first tour for a tiny bug; call model method
and call it browser coverage. Authoring → run playbook
[tour-test-authoring](tour-test-authoring.md).

**HttpCase**: hit the actual HTTP/JSON-RPC route; assert status/payload/session/auth/side
effects; auth as relevant user. Don't: HttpCase when TransactionCase proves the rule;
tour when request/response suffices.

- [ ] When uncertain about the seam, cross-check: `test_orm/tests/test_onchange.py`,
  `test_testing_utilities/tests/test_form_impl.py`, `test_orm/tests/test_ui.py` +
  `odoo/tests/common.py`.
- [ ] If a matching knowledge-base note exists for the surface, read it before writing.
- [ ] Optional: skim [reference/test-anti-patterns](reference/test-anti-patterns.md)
  if mocks, heavy fixtures, or duplicate coverage are tempting.
- [ ] Write tests from the case table, then run them via
  `odoo runtime-test --module <module> --tests <path> --output <run_dir>/runtime-test.json`
  — it wraps the known-good pytest-odoo env/db invocation, prints a short summary,
  and always saves the full structured report (raw stdout/stderr, per-test
  pass/fail JSON) to the `--output` path — no tee/redirect needed. Confirm
  **red for the right reason**
  (missing feature, not typo/setup). `HttpCase`/tour: add `--http`.
  Tour can't finish in budget → write statically, state **not executed**.
- [ ] Before a large suite or new dependency chain, run one previously green test from
  that chain (environment vs fixture diagnosis).
- [ ] Runner's raw final summary is authoritative over agent arithmetic.

## Pitfalls

- **Skipping `test-case-selection` while on this playbook is a process defect** —
  not a speed optimization. If you used `write-odoo-tests` (or dispatched a TDD
  subagent for new cases), selection must appear in the task notes.
- **Selecting cases before the feature playbook that owns them** → thin first
  table, then `followup_cycles ≥ 1` to restore create-path / dual-entrypoint
  cases. Expand feature catalogs first; prefer one complete tdd dispatch.
- Don't jump to type selection without a case table produced by selection —
  causes duplicate and dependency-owned re-tests.
- Don't default to `TransactionCase` when the bug only shows via onchange/modifier.
- Don't write a tour for something `Form` can cover.
- `Form` not raising isn't enough — assert stored values post-`.save()`.

## Relevant knowledge-base

- note: Unit Test Odoo — pytest-odoo, TransactionCase/SavepointCase, HttpCase
- note: Form Test — Form/save/x2many, modifier AssertionErrors
- note: Tour Test — tour registration, `start_tour`, tags
- `odoo runtime-test` — the known-good pytest-odoo env/db invocation (see the
  odoo-test skill; add `--http` for HttpCase/tour runs)
