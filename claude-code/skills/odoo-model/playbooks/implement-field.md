# Implement a field on a model

Applies when: adding or changing a field on a model, any ttype.

Entry point: [SKILL.md](../SKILL.md)
Called by: [implement-model](implement-model.md), [implement-wizard](implement-wizard.md)

## Usage
- used: 3
- last used: 2026-07-21

## Steps

- [ ] What logic/purpose does this field serve?
- [ ] Locate the field on the model and its `_inherit` chain (either direction). If it
  already exists, name the delta and scope the change to it. If this module only
  **extends** a model defined elsewhere via `_inherit` (and step 0 did not already
  route through `implement-model` → `inherit-model`), stop and re-route: expand
  [inherit-model](inherit-model.md) under [implement-model](implement-model.md) first,
  then resume field steps there — do not treat foreign-model extension as a bare
  field-only task.
- [ ] Reachable via an existing Many2one (`related=`) instead of duplicating?
- [ ] How is the value set — user input / code (`create`/`write`/cron) / `onchange` /
  `compute`? This decides `store=`/`readonly=`/`@api.depends`.
- [ ] `default=`, `ondelete=` (relational), `index=`, `readonly=`, `copy=` — set only
  where the intended behavior actually diverges from the ORM default; otherwise
  leave implicit. (`copy=False` when duplicating the parent record shouldn't carry
  this value over — e.g. sequence numbers, state, dates tied to the original.)
- [ ] Chatter field history (`tracking=True`)? Concrete model (or every consumer of a
  shared mixin field) must inherit `mail.thread` — otherwise Odoo logs
  `unknown parameter 'tracking'` and no track messages are posted
  (compat:tracking-without-mail-thread: `tracking=` ignored with unknown-parameter
  warning on a model without `mail.thread`, on 17/18/19 alike). Prefer putting
  `tracking=` only on thread models, not on abstract mixins reused by non-thread
  models (Mail / field tracking rule).
- [ ] Needs `domain=`, or `readonly=`/`required=` that might differ between Python and  a specific view? → run playbook: [field-constraint-placement](field-constraint-placement.md).
- [ ] Needs a constraint (`@api.constrains` or a SQL constraint — per-version form
  via compat:sql-constraints: `models.Constraint(...)` class attribute vs
  `_sql_constraints`) to keep it valid, or is validity fully covered by its
  type/domain/required already?
- [ ] Archive/unarchive via Odoo's built-in `active` field (soft-delete, not a custom
  business "Archived" state)? → run playbook:
  [add-active-field-archive](add-active-field-archive.md).
- [ ] Selection options need to narrow based on a sibling field? → run playbook:  [conditional-selection-field](conditional-selection-field.md).
- [ ] New Many2one column in an existing list view whose domain depends on a sibling
  field? → run playbook: [add-sibling-domain-many2one-field](add-sibling-domain-many2one-field.md).
- [ ] Required field on a line/child model populated by a stored compute? → run
  playbook: [missing-required-field-fallback](missing-required-field-fallback.md).
- [ ] View domain needs a value only reachable via a multi-hop relation? → run  playbook: [multihop-domain-relay-field](multihop-domain-relay-field.md).
- [ ] Changing an existing stored field's `ttype`? → run playbook:  [stored-field-type-migration](../../odoo-upgrade/playbooks/stored-field-type-migration.md) before continuing.
- [ ] Needs to show in any view at all?
- [ ] Per view shown in: does `string`/`domain`/`readonly`/`invisible` need to differ
  from the Python default? (readonly/domain asymmetry already routed above via
  field-constraint-placement; invisible is view-only; string override only if label
  truly differs — any new/changed label → run playbook: the **odoo-wlc** skill (translation round-trip).)
- [ ] Verification gate: **declarative UI / schema work** → **module-update path**;
  compute/onchange/constraint/create/write/workflow → **TDD path** then module update.

## Pitfalls

- Stored compute not implicitly view-readonly.
- `_inherit` merge can silently duplicate a field — check the full chain.
- Grep community addons for the proposed field name before inventing one (label/UX
  collisions across models).
- `tracking=True` on a model without `mail.thread` (including via mixin inheritance)
  → startup WARNING; param is ignored. Override of `_valid_field_parameter` alone
  does not enable tracking.

## Example instance

- 2026-07-10, [add-sibling-domain-many2one-field.md](add-sibling-domain-many2one-field.md):
  a new sibling-domain-filtered Many2one (`connecting_flight_id`) on a
  quick-booking line model.

## Relevant knowledge-base

- `Odoo Fields` note (vault: `6- Main doc/Odoo Fields.md`)
- `XML View` note (vault: `6- Main doc/XML View.md`) — Python-vs-XML domain/readonly
