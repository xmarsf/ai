# Create a new model

Applies when: the planned diff introduces a new concrete model/table with `_name`,
optionally combining mixin inheritance or delegated inheritance.

Parent playbook: [implement-model](implement-model.md) — this is its new-model branch; return to the next parent step after completing this checklist.

## Usage
- used: 0
- last used: n/a

## Steps

- [ ] Pick `_name` — no `x_` prefix, dot-separated, and consistent with neighboring
  models in the target module.
- [ ] Mixin behavior → `_name` + `_inherit`; delegation → `_name` + `_inherits`.
- [ ] Choose the record label and apply rule: [python] Model Identity / usable record
  label. Set `_description` and `_order` deliberately.

## Pitfalls

- Patch-in-place `_inherit` belongs to [inherit-model](inherit-model.md).

## Example instance

- (seed entry — fill in with the first orchestrated run that creates a wholly new
  model, including the model name, inheritance shape, and shared parent steps used.)

## Relevant knowledge-base

- note: Odoo Model — `_name`/`_inherit`/`_inherits` semantics, table creation.
- source: `odoo/orm/model_classes.py:_setup` (path per compat:orm-module-layout —
  `odoo/orm/` layout on 19, `odoo/models.py` on 17/18)
  — record-name setup and `name` priority.
- `Odoo Extensible Inheritance` note (vault: `6- Main doc/Odoo Extensible Inheritance.md`)
