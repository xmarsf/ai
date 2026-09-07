# model-technical-rename

Applies when: renaming an Odoo technical model name (e.g. `old.prefix.model` to
`model`) while preserving data in databases where the module is already installed.

Parent playbook: [implement-model](../../odoo-model/playbooks/implement-model.md) — alternative branch; matching this condition stops/replaces the remaining parent path.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Map every `_name`, `_inherit`, relational comodel, `self.env[...]`, XML
   `model`/`res_model`, security CSV model id, generated model/field XML id, sequence
   code, and cross-addon dependency reference before editing.
- [ ] Rename Python/XML files and update manifests/imports in the same pass; plan
   SQL table/data migration together with the model rename (table name derives from
   `_name` — source: `model_classes.py:_init_model_class_attributes` below).
- [ ] Add a new migration version when the installed database may already be at the old
   module version. A migration in an already-installed version directory will not prove
   the current upgrade path.
- [ ] Make rename migrations idempotent for partial failed upgrades: if an empty new table
   exists, drop it before renaming the old table; if new metadata already exists, update
   references without blindly updating unique `ir_model.model` rows.
- [ ] Run module update before create/search tests; registry-only tests can pass even when
   renamed SQL tables have not been created or renamed yet.
- [ ] Verify with stale-reference greps excluding migrations and intentional negative tests,
   then run touched module tests and dependency tests that use the renamed models.

## Pitfalls

- A registry test can pass while broader tests fail with `UndefinedTable` because the
  database schema was not upgraded.
- Straight `UPDATE ir_model SET model = new WHERE model = old` can fail if a previous
  failed upgrade created the new metadata row.
- Deleting stale `ir_model` rows directly can trip action/cron foreign keys; let Odoo's
  cleanup handle stale rows after references are moved.

## Relevant knowledge-base

- source: `odoo/orm/model_classes.py:_init_model_class_attributes` (path per compat:orm-module-layout)
- source: `odoo/addons/base/models/ir_model.py:model_xmlid`
