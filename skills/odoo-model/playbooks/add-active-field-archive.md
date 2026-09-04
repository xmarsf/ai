# add-active-field-archive

Applies when: the request is to "archive"/"unarchive" or "soft-delete" a business
document model that has no Odoo `active` field yet, and the desired behavior is
Odoo's standard built-in archive mechanism (not a custom business "Archived" state).

Called by: [implement-model](implement-model.md), [implement-field](implement-field.md)
— returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: 2026-07-17

## Steps

- [ ] **Confirm scope with the user before touching code** if the model already has a
  terminal workflow state (cancelled/rejected/expired/etc.) — "archive" is ambiguous
  between Odoo's standard `active` toggle (no state restriction), a business rule
  gating archive to a terminal state, or an unrelated concept. Use `AskUserQuestion`;
  don't guess.
- [ ] **Add `active = fields.Boolean(default=True)`** to the model, placed near other
  simple/scalar fields (not inside a One2many/relational block).
- [ ] **Wire the standard archive UI in every relevant list/form view.** Include
  `active` in each view architecture (normally invisible; use
  `column_invisible="True"` in a list) so the web client exposes Archive/Unarchive.
  Add or verify a search-view **Archived** filter with domain
  `[('active', '=', False)]`, so users can reach inactive records and unarchive
  them. See the source pointers below.
- [ ] **Check `ir.model.access.csv`** — usually no change needed (note below).
- [ ] **Audit every plain `self.search([...])` call already in the model** (crons,
  `@api.constrains` cross-record checks, scheduled state-transition methods) for
  whether silently excluding an archived record changes business behavior. Flag any
  hit to the user as a should-fix finding during `odoo-review` rather than silently
  accepting or "fixing" it — which state a record was archived from is the user's
  call.
- [ ] **One2many/Many2many child listings on a parent are not affected** — no special
  handling needed there (note below).
- [ ] **If archive is gated by business state** (e.g. only `stopped`/`done` may
  archive): enforce server-side through a shared helper called from **both** `create`
  and `write`; `@api.constrains` may complement but never replace those guards.
  `write()` alone is not enough — `create({..., 'active': False})` bypasses it. Apply
  rule: `[python] Never rely on @api.constrains alone…`. Detect an archive request
  by key presence plus falsiness (`'active' in vals and not vals['active']`), not
  identity with the `False` singleton; ORM callers may supply `0`.
- [ ] **Bump the module version** per the **odoo-wlc** skill (manifest-and-translation-hygiene flow).
- [ ] **Test type: `TransactionCase`.** These rows are **owned cases for
  test-case-selection** (expand this playbook *before* selection when TDD runs at
  step 3 — see [write-odoo-tests](../../odoo-test/playbooks/write-odoo-tests.md)). Cover:
  - new record defaults `active=True`;
  - default `search()` excludes an archived record; `with_context(active_test=False)`
    includes it (ORM `active_test` seam — one pair is enough);
  - `action_archive()`/`action_unarchive()` toggle the field.
  When archive is **state-gated**, also **own** (do not drop as framework):
  - archive blocked from non-terminal states (write/action path);
  - direct `write({'active': False})` is blocked from non-terminal states (the
    server-side entrypoint, independent of the action wrapper);
  - **`create({..., 'active': False})` from a non-allowed state is blocked** (create
    path — required; missing this is the usual follow-up-cycle tax);
  - one explicit non-Boolean falsy value such as `active=0` follows the same blocked
    create path (guards against an `is False` implementation);
  - unarchive unrestricted unless the user required otherwise.
- [ ] **When this playbook is on the TDD path:** put the state-gated create-path row
  in the **first** case table. Do not ship a thin archive table and restore
  create-path in a follow-up dispatch.
- [ ] **Upgrade the test DB module (`-u <module>`) before running tests** — the new
  column doesn't exist until then (`odoo runtime-test --init update`, or `odoo
  module update` first). If `-u` fails on an
  unrelated pre-existing issue, surface it to the user rather than working around it
  with a raw `ALTER TABLE`.

## Pitfalls

- Don't infer Archive/Unarchive availability from the model field alone.
  compat:archive-active-field-view (web list/form controllers enable Archive/Unarchive
  only when `active` (or `x_active`) is present in the loaded view fields, on
  17/18/19 alike);
  keep the field in each relevant architecture even when invisible.
- Don't assume archiving needs new ACL rows — check existing `perm_write` first.
- A `write()`-only archive guard looks complete until someone creates a record already
  inactive — always cover the create path when the invariant is state-gated.
- Treating create-with-`active=False` as "ORM/framework" so it is dropped from the
  first case table — it is **your** guard; dropping it forces a second tdd cycle.
- Expanding this playbook only after the first tdd dispatch — then discovering
  create-path mid-implement.

## Example instance

- 2026-07-09: a `contract` model and a `quotation` model in two custom addons both
  gained `active = fields.Boolean(default=True)`. User confirmed via
  `AskUserQuestion`: standard archive, no state restriction. Review flagged
  (should-fix, not blocking) that the contract's cron state-transition methods and
  its cross-record overlap check all use plain `search()` and will silently stop
  seeing an archived contract even if its `state` is still `active` — accepted as
  intended archive semantics per the user's explicit "no restriction" choice, not
  fixed.

## Relevant knowledge-base

- Default filtering and archive actions: source
  `odoo/orm/models.py:BaseModel._search` (path per compat:orm-module-layout),
  `BaseModel.action_archive`, and `BaseModel.action_unarchive`.
- List/form UI availability: source
  `addons/web/static/src/views/list/list_controller.js:ListController.setup`
  and
  `addons/web/static/src/views/form/form_controller.js:FormController.archiveEnabled`.
- Loaded view fields: source
  `odoo/addons/base/models/ir_ui_view.py:View._get_view_fields`.
