# test-performance-verify

Applies when: reviewing, auditing, or authoring Odoo tests for speed, isolation, and
parallel safety under `pytest-odoo` / `pytest-xdist` (Odoo 19 idioms). Run it as the
**review pass after** the case table is built ([test-case-selection](test-case-selection.md))
and the tests are written, or when a suite is slow or flaky under xdist.

Entry point: [SKILL.md](../SKILL.md), [write-odoo-tests](write-odoo-tests.md)

## Usage
- used: 0
- last used: never

## Review checklist (apply to every test file in the diff)

1. **No `HttpCase` / `browser_js()` for backend or API checks.** Headless Chrome plus a
   local HTTP socket costs ~30s. Use `TransactionCase` and call the controller or model
   method directly. Tours only for OWL/JS widgets that server-side logic cannot prove
   ([tour-test-authoring](tour-test-authoring.md)).
2. **No `.create()` / DDL in `setUp(self)`.** It re-runs for every test method. Build
   shared fixtures in `@classmethod setUpClass(cls)`. Allowed in `setUp`: mocks
   (`patch`), time freezes, `registry.clear_cache()`, per-test re-binding (§1.3).
3. **No redundant `self.env.flush_all()`.** Reading ORM fields resolves computes and
   caches in memory. Flush only before raw SQL (`cr.execute`) or right before
   `invalidate_all()` in a reload test.
4. **`.new({...})` for pure computes, math, formatters, onchange logic.** Zero SQL
   `INSERT`, zero sequence use.
5. **Only primitives in `self.subTest(...)`** (int, str, bool, float, ISO date string).
   `date`, recordsets, cursors raise `DumpError` under xdist. Use
   `fields.Date.to_string(d)`.
6. **Fake models via native v19 registration** in `setUpClass` (§6). Never a throwaway
   test addon.
7. **No global context mutation in shared base/Common classes**
   (`cls.env = cls.env(context=...)`). Context keys leak into core ORM behavior
   (e.g. BoM cycle validation). Scope context changes to the concrete test class, or
   use `with_context(...)` at the call site.
8. **`Form(...)` only for client-view behavior** (onchange chain, modifiers). Never as a
   record builder — it parses arch and fires interactive onchange (5x–10x slower, 1.5–3s
   per `save()`). Use `.create()` / `.write()`.
9. **No heavy infrastructure in fixtures.** `stock.warehouse` and `res.company` cascade
   into routes, picking types, sequences, journals. Use a plain `stock.location` child or
   the default company unless routing/multi-company is the thing under test.
10. **Vary unique-index dimensions in sibling records** (shift, date, code, sequence).
    Read the model's SQL constraints first; helpers take `**kwargs` so siblings differ.
11. **Sync `tests/__init__.py`.** Every `test_*.py` must be imported there — pytest finds
    unimported files, `odoo-bin --test-enable` silently skips them. Diff the directory
    listing against the imports.
12. **No `set_param()` in `setUp(self)`.** Set config once in `setUpClass`; savepoint
    rollback undoes per-test overrides.
13. **Pure logic → `unittest.TestCase`.** Stdlib-only utilities (num2words, regex,
    formatters) must not inherit `TransactionCase` / `AccountTestInvoicingCommon` (10s+
    accounting setup for a <1ms test).
14. **Disable mail tracking on tracked models** (`mail.thread`, `mail.activity.mixin`)
    unless chatter is asserted (§11). ~10x faster writes.
15. **No `res.config.settings.execute()` / bare `set_values()`** — they walk 500+ fields
    across all addons (+1.5–2.5s per test). Assert `_fields[name].config_parameter`, or
    `default_get([...names])`.
16. **No micro-test files.** 1–3 method files each inheriting a heavy Common rebuild the
    fixture graph (+0.5–1.0s per class). Consolidate related lifecycles into one class.
17. **`get_view()` over `get_views()`** for single-view inspection — `get_views()` runs
    `fields_get()` on the model and sub-views (+0.5–2s per call). Pure XML checks:
    `view.get_combined_arch()`.
18. **No mid-test group mutation on `self.env.user`.** Writing `group_ids` clears
    ir.rule, `has_group`, and ACL caches. Create role users in `setUpClass` and call
    `record.with_user(cls.manager_user).action_*()`.
19. **Amortize file generation/parsing in parameterized tests.** Build one composite
    payload (openpyxl, reportlab, QWeb render) outside the loop; mutate only target
    cells per `subTest`. No per-iteration DB records for invalid-input loops.

## Patterns

### §1.3 Reuse class-level records across tests (`with_env`)

The per-test savepoint rolls DB state back to the `setUpClass` snapshot, so a record built
once can be mutated (e.g. `action_post()`) inside a test and is draft again for the next.
Only re-bind it to the test's env:

```python
@classmethod
def setUpClass(cls):
    super().setUpClass()
    cls.invoice = cls._create_invoice()

def setUp(self):
    super().setUp()
    self.invoice = self.invoice.with_env(self.env)
```

This is the sanctioned exception to "do not mutate `setUpClass` records in methods"
in [test-module-structure](test-module-structure.md). It covers **DB rows changed inside
a test**; class-level changes to existing master data made in `setUpClass` itself still
need the `tearDownClass` restore.

### §2 `.new()` for compute tests

```python
line = self.env["quotation.meal.line"].new({
    "base_markup": 1.5, "base_profit_factor": 1.25, "pricing_method": "by_cost",
})
line._compute_unit_price()
self.assertEqual(line.unit_price, 12.5)
```

### §6 Odoo 19 fake model

```python
from odoo.orm.model_classes import add_to_registry

@classmethod
def setUpClass(cls):
    super().setUpClass()
    from .fake_models import FakeModel

    add_to_registry(cls.registry, FakeModel)
    cls.registry._setup_models__(cls.env.cr, [FakeModel._name])
    cls.registry.init_models(cls.env.cr, [FakeModel._name], {"models_to_check": True})
    cls.addClassCleanup(cls.registry.__delitem__, FakeModel._name)
```

Do NOT convert an existing core model (`_name = "res.partner"`) to abstract
(`TypeError` in `_check_model_extension`), and do not add dummy addons to `addons_path`.

### §11 Tracking off (concrete test class, per rule 7)

```python
@classmethod
def setUpClass(cls):
    super().setUpClass()
    cls.env = cls.env(context=dict(
        cls.env.context,
        tracking_disable=True, mail_create_nolog=True,
        mail_create_nosubscribe=True, mail_notrack=True,
    ))
```

Keep tracking on only in tests that assert `message_post()` / follower notifications.

### §5 xdist-safe `subTest`

```python
with self.subTest(date_str=fields.Date.to_string(record.date_field)):
    ...
```

### §12 `res.config.settings` fast assertions

```python
fields = self.env["res.config.settings"]._fields
self.assertEqual(fields["day_from"].config_parameter, "sca_quotation.day_from")
defaults = self.env["res.config.settings"].default_get(["day_from", "day_to"])
```

### §15 Role users instead of group mutation

```python
record.with_user(self.qc_manager).action_verify()   # qc_manager built in setUpClass
```

### §16 One template, mutate per case

```python
inspection = self._excel_inspection(tuple(c[0] for c in cases))  # once
for result_type, invalid_val, error in cases:
    with self.subTest(result_type=result_type):
        wb = self._excel_workbook(inspection)   # mutate target cell only
```

## Verification

- [ ] Grep the diff for the greppable violations: `HttpCase|browser_js`, `def setUp` bodies
      containing `.create(|set_param|write(`, `flush_all`, `Form(`, `\.execute\(\)`,
      `get_views\(`, `group_ids`, `subTest\(` with non-primitive kwargs.
- [ ] Compare `ls tests/test_*.py` against `tests/__init__.py` imports.
- [ ] Run the touched files via `odoo runtime-test --module <m> --tests <path>` and
      compare durations before/after; with xdist, confirm no `DumpError`.
- [ ] Report each finding as rule number + file:line + fix; do not rewrite tests outside
      the diff.

## Related

- [test-anti-patterns](reference/test-anti-patterns.md) — correctness-side checklist
- [test-module-structure](test-module-structure.md) — layout, Common, `setUpClass`
- [write-odoo-tests](write-odoo-tests.md) — type selection
