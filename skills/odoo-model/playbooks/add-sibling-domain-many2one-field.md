# Add a sibling-domain-filtered Many2one field + list column

Applies when: adding a new Many2one column to an existing list/editable-list view,
where the field's default filtering derives from *other fields already on the same
record* (same category / same date / later timestamp, etc.).

Parent playbook: [implement-field](implement-field.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] **Locate the real target view/model — don't trust the file the user names or
   has open in their IDE.** Grep all modules for the literal column label the user
   describes before assuming the named file is the target.
- [ ] Read the target model's Python file fully to find the sibling fields the new
   domain must reference, and check whether an existing method on the model already
   searches the same comodel — any extra filter that method applies (e.g. a type
   discriminator on the comodel) probably belongs in the new domain too; it won't be
   obvious from the user's request alone.
- [ ] run playbook: [field-constraint-placement](field-constraint-placement.md) — decide whether the domain belongs in
   the Python field, the XML view, or a shared search-view filter, before writing it.
- [ ] Write the domain referencing sibling fields **without** a `parent.` prefix —
   that prefix is only for one2many sub-line→parent references (knowledge-base
   `Odoo domain` note). Verify insertion position by re-reading surrounding view
   lines after editing — easy to insert one field too late.
- [ ] **Guard numeric sibling fields used in domain comparisons against being unset**
   — unset Float is 0.0, not falsy-but-empty (knowledge-base `Odoo Fields` note).
- [ ] "Search More" popup: Odoo reuses the comodel's one registered default search
   view automatically — no wiring needed. To expose extra filter fields there, add
   `<field>` entries to that search view (confirm which search view is the default
   if the comodel has several).
- [ ] A pure field+domain+view change with no compute/constrains logic has no
   testable behavior change (TDD skip criterion) — go straight from plan
   to implementation.

## Pitfalls

- If the target module already violates an i18n/string convention wholesale (literal
  translated `string=` everywhere, no `i18n/*.po` at all), don't invent the missing
  infra for one new field — flag the module-wide inconsistency in the report instead
  of silently fixing scope you weren't asked to touch.

## Example instance

- 2026-07-05: the user pointed at one views file (open in IDE) but the real
  quick-booking screen was a different model in another views file — found by
  grepping the described column label. Sibling fields were
  airline/aircraft/date/ETD; the existing auto-fill method already filtered the
  comodel by `schedule_type = 'day'`, which the new domain needed
  too. Review caught the one real bug: an unset-Float ETD comparison. The
  domain-in-Python choice was later corrected to a shared search-view filter per
  [field-constraint-placement.md](field-constraint-placement.md).

## Relevant knowledge-base

- `Odoo domain` note — `parent.` prefix only applies to one2many sub-lines
  referencing the parent record, not sibling top-level fields.
- `Odoo Fields` note — "Unset Float is 0.0, not falsy-but-empty".
