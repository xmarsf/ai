# Cross-module test ownership and shared setup

Applies when: the behavior under test spans addons, `_inherit`s a model owned
elsewhere, lives in a bridge/glue module, or a shared-model change may affect
dependents. Use after case selection to place tests and decide re-run vs re-author.

Parent playbook: [write-odoo-tests](write-odoo-tests.md) — returning sub-step; resume
the next parent step after this checklist.

## Usage
- used: 1
- last used: 2026-07-16

## Steps

- [ ] Identify the **owner module**: the addon that **adds** the behavior (new
  method, override, field with business meaning, glue between two apps). Tests
  live there. Tests cannot depend on modules the owner does not depend on.
- [ ] Apply the placement matrix:

  | Situation | Test lives in | Setup | Assertions |
  | --- | --- | --- | --- |
  | New model/rule in A | A | A's Common | A's outcomes only |
  | A `_inherit`s B, adds delta | A | inherit B's Common if A depends on B | only A's delta |
  | Glue C depends on A+B | C | `class CCommon(ACommon, …)` | only A↔B integration |
  | Bug only with D installed | D, or owner with `post_install` | full graph | the interaction |
  | Shared model used by E, F | owner of the change | — | re-run E/F suites; **do not copy** their cases |

- [ ] **Share fixtures, not cases.** Downstream Common inherits upstream Common
  and adds helpers (`_make_*`, `_so_deliver`-style). Do not copy-paste sibling
  `test_*` methods into another module.
- [ ] For each case row from [test-case-selection](test-case-selection.md): if the
  outcome is already asserted in a dependency, cite `module:Class.method` and
  drop the row. "Covered elsewhere" is explicit, not assumed.
- [ ] Tags: interaction that can change when more modules install → prefer
  `at_install` when the invariant must hold early; full-stack / HttpCase /
  multi-module glue often uses `post_install` + `-at_install` (see Odoo tags).
- [ ] After implementing a change on a **shared model**, grep dependents for the
  model `_name` / key method and **re-run** their focused tests. Execution ≠
  re-authoring.
- [ ] Two modules asserting contradictory outcomes → `AskUserQuestion`; do not
  "fix" by weakening the other suite silently.
- [ ] Structure details (file layout, setUpClass isolation) →
  [test-module-structure](test-module-structure.md).

## Pitfalls

- Re-implementing dependency happy paths "for safety" doubles suite time and
  drifts when the dependency changes.
- Putting glue assertions in A or B when only C depends on both — untestable if
  C is not installed; place in C.
- Inheriting the heaviest upstream fixture graph when the delta needs one record.
- Assuming Runbot/CI installs modules outside your depends — only dependants you
  declare are guaranteed in isolated installs.

## Example instance

- Core: `sale_stock` inherits `TestSaleCommon` + stock fixtures; tests SO↔delivery
  only, not pure pricing (sale) or pure quant (stock).
- Custom suite: quotation/contract commons extend a shared menu-management Common; each asserts its
  chain delta only.

## Relevant knowledge-base

- note: Unit Test Odoo — modular tests, post_install / at_install
- Odoo tutorial "Modules" section — tests modular; no undeclared depends
