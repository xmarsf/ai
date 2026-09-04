# Odoo test anti-patterns

Applies when: writing or reviewing Odoo tests — an anti-pattern checklist to load
when mocks, heavy fixtures, duplicate coverage, or "green but wrong-seam" tests are
tempting (review subagent, main agent). Not a
playbook — no usage counter. Process entry: [write-odoo-tests](../write-odoo-tests.md).

## Iron rules

1. Assert **business outcomes**, not "did not raise".
2. Do not re-test the **ORM** or behavior **owned and covered** by a dependency.
3. Prefer **real entrypoints** over mocks and `skip_*` shortcuts unless the case is
   only about a guard that needs forced state.
4. Never add **test-only methods** to production models — put helpers on test Common.

## Anti-patterns

| Anti-pattern | Why it fails | Fix |
| --- | --- | --- |
| Assert only no-exception | Passes while wrong values stored | Assert state/fields/errors |
| Form/tour for pure backend | Wrong seam; expensive | TransactionCase at the method |
| Tour for plain onchange | Slow, flaky, overkill | `Form` |
| Full lifecycle for one guard | Noise; hides the branch | One method + minimal fixture |
| Assert every field | Brittle; unrelated compute noise | Fields that prove the rule |
| Heaviest sibling fixture always | Slow; false deps | 1–2 records; dual light/heavy OK |
| Copy dependency `test_*` into this module | Duplicate runs; drift | Inherit Common; re-run theirs |
| Mutate `setUpClass` records in methods | Leak across tests | Fresh records per mutating test |
| Mass-write existing master data in `setUpClass` with no restore | Pollutes later classes / re-runs | Snapshot on `cls`; restore in `tearDownClass` before `super()` (or avoid mutation) |
| Prefer `addClassCleanup` for business-fixture restore | Hidden side effects; harder to review | `tearDownClass` for fixture restore; `addClassCleanup` for patches/cursors |
| Rely on demo / residual DB data | Order- and DB-dependent | Create all needed data |
| `cr.commit` in tests | Breaks isolation | Never |
| Test mock/skip wrapper behavior | Proves the skip, not the product | Real action when asserting flow |
| Partial fixture missing discriminators | Wrong branch silently | Set state/company/group explicitly |
| Coverage % as success | Empty tests green | Case table from selection playbook |

## RED verification

Before calling a test "good red":

- Fails (not errors on import/setup).
- Failure reason is **missing/wrong feature**, not NameError / invalid field / missing XMLID.
- One previously green test in the same chain still collects if the env is new.

Wrong failure → fix the test, do not implement production code yet.

## Related

- [test-case-selection](../test-case-selection.md) — what cases
- [test-module-structure](../test-module-structure.md) — layout/fixtures
- [test-cross-module](../test-cross-module.md) — ownership
- Test Isolation rule (see test-module-structure) — no mutating class-level fixtures
