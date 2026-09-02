# Place tests and shared fixtures in a module

Applies when: writing or extending Odoo tests and the target addon needs
`tests/` layout, file split, `common.py`, `setUpClass` / `tearDownClass` vs
per-method data, tags, or tour asset wiring. Fires after case selection; before
or while authoring files.

Parent playbook: [write-odoo-tests](write-odoo-tests.md) — returning sub-step; resume
the next parent step after this checklist.

## Usage
- used: 3
- last used: 2026-07-17

## Steps

- [ ] Confirm package layout under the **owner module** (module that adds the
  behavior — see [test-cross-module](test-cross-module.md)):

  ```
  <module>/
  ├── tests/
  │   ├── __init__.py          # import every test_* module
  │   ├── common.py            # shared fixtures/helpers (when reused)
  │   └── test_<scope>.py
  ├── static/tests/tours/      # tours only
  └── __manifest__.py          # web.assets_tests for tours
  ```

  Do not import `tests` from the module root `__init__.py`.

- [ ] **Split files by scope** (`test_rfq_state.py`, `test_contract_constraints.py`),
  not one mega-file. Prefer the addon's most recent similar file for
  `@tagged(...)`, `BaseCommon` vs raw `TransactionCase`, helper style.
- [ ] Prefer a **module `Common` class** in `tests/common.py` when ≥2 test classes
  share partners/products/helpers. Pattern: inherit upstream Common when the module
  depends on that addon (core: `ProductCommon` → `SaleCommon`; custom suites: a
  shared menu-management Common → chain commons).
- [ ] **`setUpClass`**: expensive, read-mostly shared records only. Do not put
  fixtures there that test methods mutate (Test Isolation rule).
  Per-method create/copy for state you will change. Use `tracking_disable` unless
  tracking is under test. Set branch discriminators explicitly.
- [ ] **`tearDownClass` for temporary class-level side effects.** When
  `setUpClass` must change **existing** master/shared rows (e.g. zero other meal
  types' ETD ranges so exactly one fixture matches), snapshot originals on `cls`
  and restore them in `tearDownClass`, then call `super().tearDownClass()`. Prefer
  this over `addClassCleanup` for business-fixture restore — one obvious place,
  matches usual unittest style. Reserve `addClassCleanup` for infrastructure
  (stop a `patch()`, close a cursor, leave registry test mode) the way Odoo core
  does in `odoo/tests/common.py`. Prefer create-only fixtures or a method patch
  when you can avoid mutating shared master data at all.
- [ ] Keep fixtures **minimal**: target addon's Common + 1–2 records. Light and
  heavy fixtures may coexist (guard-only tests vs full lifecycle) — do not force
  every test through the heaviest sibling.
- [ ] Helpers: `_make_<record>(**vals)` / small action helpers on Common — not
  test-only methods on production models.
- [ ] Tags: default `standard` + `at_install`. Use
  `@tagged('post_install', '-at_install')` when the behavior needs the full install
  graph, HttpCase/tours, or must not run mid-install. Module-specific tags (e.g.
  the addon's technical name) are fine alongside.
- [ ] Tours: JS under `static/tests/tours/`, register `web.assets_tests`, Python
  runner via [tour-test-authoring](tour-test-authoring.md).
- [ ] Ground Form/tour syntax via knowledge-base notes before writing from memory.

## Pitfalls

- `setUpClass` mutations leak across methods (savepoint isolation does not restore
  class-level records the way people expect for in-place writes).
- Mass-writing existing master data in `setUpClass` without `tearDownClass`
  restore pollutes the DB for later classes / the same class if setup is re-run.
- Forgetting `super().tearDownClass()` (or restoring after super tears down
  env/cursor) — restore shared rows **before** `super().tearDownClass()`.
- Using `addClassCleanup` for business-fixture restore when a single
  `tearDownClass` would be clearer; the reverse is fine for patch/cursor stacks.
- Copying the heaviest sibling fixture for a one-field guard wastes time and hides
  the real seam.
- Missing `tests/__init__.py` import → test never collected.
- Demo/residual DB data as implicit fixture — always create what you need.

## Example instance

- Custom suite: a menu-management addon's `tests.common.MenuManagementCommon` →
  a contracts addon's `ContractChainCommon` /
  a quotation addon's `QuotationChainCommon` with `_make_*` helpers.
- Meal-type isolation: a custom suite Common's `_isolate_meal_type`
  snapshots ETD ranges → `tearDownClass` restores (not bare mass-write).
- Core: `product.tests.common.ProductCommon` → `sale.tests.common.SaleCommon` →
  `sale_stock.tests.common.TestSaleStockCommon`.

## Relevant knowledge-base

- note: Unit Test Odoo — TransactionCase/SavepointCase, tags, HttpCase
- note: Form Test / note: Tour Test — when those surfaces apply
- `odoo runtime-test` — the known-good pytest-odoo env/db invocation (see the odoo-test skill)
- source: `odoo/tests/common.py` — TransactionCase, tagged, HttpCase
