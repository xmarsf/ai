# shared-line-model-second-parent

Applies when: a child/line model already required by one parent (Many2one `required=True`,
e.g. `line.parent_a_id`) gets extended via `_inherit` to also be attachable to a second,
different parent model (a new `line.parent_b_id` Many2one, wired up via that second
parent's own `One2many(..., inverse_name='parent_b_id')`). Creating a row from the second
parent's one2many only populates `parent_b_id` — the original `parent_a_id` stays empty
and its `required=True` blocks the create. Distinct from `merge-submodel-into-shared-model`
(that's about folding one *existing* submodel into an unrelated sibling model wholesale,
not adding a second optional parent link to a model that already has one required parent).

Parent playbook: [inherit-model](inherit-model.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Before picking XOR vs OR for the "which parent(s) must be set" invariant, grep for a
   promotion/conversion flow between the two parent models that might reattach existing child
   rows from parent A to parent B without clearing parent A's link. If one exists, the correct
   invariant is OR ("at least one set"), not XOR — don't assume XOR from a bug report that only
   shows the second-parent-empty case.
- [ ] Relax `required=True` only in the module that introduces the second parent, not the base
   model (check the `depends` direction) — override via the field kwarg in the `_inherit`
   extension. note: Odoo Fields (kwarg-merge semantics for `_inherit` field overrides).
- [ ] Enforce the "at least one parent" invariant with a DB CHECK constraint
   (compat:sql-constraints — `models.Constraint(...)` class attribute on 19,
   `_sql_constraints` on 17/18), not
   `@api.constrains` — a `create()` that omits both parent fields skips Python constrains
   entirely but not a DB CHECK.
- [ ] If another field on the shared model uses `related=` through the original single parent,
   it resolves empty for second-parent-only rows — override it in the same `_inherit` extension
   as `compute=...`, explicitly clearing `related` and repeating `comodel_name`. Fall back to
   whichever parent is set, and confirm which parent should win when both are (don't default to
   source order). note: Odoo Fields (`related=False` clearing + comodel_name caveat).
- [ ] If that field also moves from `related=` to `compute=..., store=True` (new DB column),
   check whether Odoo's schema sync already backfilled existing rows (`SELECT count(*) WHERE
   new_column IS NULL` after a plain `-u` upgrade) before assuming a `post-migrate.py` is
   mandatory — add one anyway as cheap defensive coverage regardless.
- [ ] Remember schema/constraint changes don't take effect on an already-running dev/test DB
   until the module is upgraded (`-u <module>`) — a stale-schema failure can look like the code
   fix didn't work.
- [ ] run playbook: the **odoo-wlc** skill (manifest-and-translation-hygiene flow) — version bump, `.po` entry for the
   new constraint message, pylint pass.

## Pitfalls

- An XOR-first invariant tends to get caught late, by a TDD run against pre-existing data that
  already has both parents set from a conversion flow — check for that flow before writing the
  constraint, not after a test fails.
- `@api.constrains` silently misses a `create()` that omits both parent fields; only a DB
  CHECK constraint (compat:sql-constraints) catches it unconditionally.

## Relevant knowledge-base

- `Odoo Fields` note (vault: `6- Main doc/Odoo Fields.md`) — "Overriding a field's kwargs from an `_inherit` extension model
  merges, doesn't replace" section: source-cited (`odoo/orm/fields.py:Field._get_attrs`) mechanics for
  the kwarg-merge behavior, the `related=False` clearing caveat, and the required-vs-constrains
  independent-gates note.

## Example instance

- 2026-07-09 — a quotation supplement line model (`quotation_id` set
  required=True) blocked creation from a second parent's one2many (inverse
  `contract_id`, added by a bridging addon's `_inherit` extension). Root-caused via
  the bridge module's `_create_contract()`, which reattaches
  a quotation's existing supplement lines to a new contract via
  `lines.write({'contract_id': contract.id})` without clearing `quotation_id` — proving the
  real invariant was OR, not XOR, after an XOR-first attempt failed against that exact data
  shape in the TDD run. Fixed with a `quotation_id = fields.Many2one(required=False)` override,
  a DB CHECK OR-constraint (compat:sql-constraints), and a `currency_id` related→compute override preferring
  the contract's currency. Odoo's `_auto_init` had already backfilled the one pre-existing
  row's new stored `currency_id` column during an earlier upgrade in the same session; a
  defensive `post-migrate.py` was added anyway.
