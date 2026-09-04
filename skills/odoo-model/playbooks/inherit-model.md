# Inherit an existing model

Applies when: a task adds fields, methods, or overrides behavior on a model defined
**elsewhere** (core, community addon, or another addon module) via `_inherit`, rather
than creating a new model. Does **not** apply when the module already owns the model
(defines its `_name`) and the task edits that class directly in place — that has no
`_inherit` mechanics to check and stays in [implement-model](implement-model.md)'s own
steps; do not log this playbook as used for that case.

Parent playbook: [implement-model](implement-model.md) — this is its existing-model branch; return to the next parent step after completing this checklist.

## Usage
- used: 0 (tracking started 2026-07-13)
- last used: n/a

## Steps

- [ ] Existing identity → patch-in-place branch (not a new `_name`). Prefer
  **string** `_inherit = 'existing.model'` (MetaModel auto-fills `_name`).
- [ ] Also needs abstract mixin(s) on the same identity → set
  `_name = 'existing.model'` **and** `_inherit = ['existing.model', 'mixin…']`.
  Do not use list `_inherit` alone without `_name` (compat:inherit-list-form:
  list-form `_inherit` without explicit `_name` logs a startup warn on 19 and infers
  identity from the Python class name; 17/18 infer silently).
- [ ] Extends a child/line model so it can belong to a second parent? → run playbook:
  [shared-line-model-second-parent](shared-line-model-second-parent.md).
- [ ] Simplifies an over-engineered selection flow on an existing line model? → run
  playbook: [simplify-line-submodel](simplify-line-submodel.md).

## Pitfalls

- Explicit `_name` that is **not** the model being patched (and not in `_inherit`)
  means this is **not** the patch-in-place branch — return to parent classification.
- Startup warn `Class X has no _name, please make it explicit` → almost always
  list-form `_inherit` without `_name`. Code can still work if class CamelCase
  maps to the real model; silence with explicit `_name` or switch single-parent
  lists to string form. See knowledge-base pointers below.
- A bug fix or new branch added directly inside a method on the module's own owning
  model (editing the file that defines `_name`, no separate `_inherit` extension
  file) is **not** this playbook — it's a false match on "patches an existing model
  in place" from [implement-model](implement-model.md)'s old branch wording. Don't
  bump this playbook's usage counter for that shape; its checklist (list vs string
  `_inherit`, mixins) has nothing to check when there is no `_inherit` at all.

## Example instance

- 2026-07-17: startup warns fired on `ProductTemplate` / `ResPartner` /
  `PurchaseOrder` / `StockPicking` / `AccountMove` extensions — all list
  `_inherit` without `_name` across several custom addon modules (still extending
  the standard models via class-name inference).

## Relevant knowledge-base

- `note: Odoo Extensible Inheritance` — §3 list vs string `_inherit`, list-form
  warn path (see compat:inherit-list-form above)
- `note: Model - Inheritance & Registration Helpers` — `MetaModel.__new__` resolution
- `source: odoo/orm/models.py:MetaModel.__new__` (path per compat:orm-module-layout)
