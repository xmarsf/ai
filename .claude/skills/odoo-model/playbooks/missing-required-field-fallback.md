# Missing required field populated by a stored compute

Applies when: a required field on a child/line model is populated by a stored compute
(often `precompute=True`) that only fires under certain conditions, and saves crash
with a DB `NotNullViolation`. Two known sub-shapes:

**Sub-shape A — the compute reads an optional field on a related record**, so the
value chain can legitimately come up empty (source field unset → required target
field empty).

**Sub-shape B — the compute simply skips when its trigger field is unset**, and a
user-facing editable list lets the user save a row without that trigger field
because the view never shows the computed field and never marks the trigger field
required.

The symptom (missing required field) is identical for both — trace which
one2many/list the user actually interacted with before assuming the cause.

Parent playbook: [implement-field](implement-field.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Trace the error backward from the crash: the method named in the error/user
   flow is often not where the value is set. `create()` on a parent can trigger
   stored `@depends` computes that populate one2many lines well after the "obvious"
   method returns — follow the `@depends` chain to the actual `Command.create` call
   site.
- [ ] **Before assuming a sub-shape, verify against real data** if a live/test
   instance is reachable — run playbook: [xmlrpc-live-query](../../odoo-debug/playbooks/xmlrpc-live-query.md). Query the actual child
   rows implicated and check whether they violate the assumed invariant. Don't skip
   this just because one sub-shape matches the field name in the error message.
- [ ] Check the *source* model's required-ness for the field being read, not just
   the field being written. A DB constraint is often looser than it looks (one field
   required OR another, not both) — read the constraint text directly.
- [ ] For sub-shape A, when adding a fallback chain (`a or b or c`): enumerate every
   *row shape* that can reach the code, not just the one in the bug report. Child
   models using the standard `display_type == 'line_section'` convention have a
   disjoint required-field set for section rows — grep sibling consumers of the same
   child model for `.filtered(lambda x: not x.display_type)` before considering the
   fix complete.
- [ ] apply rule: [python] never rely on `@api.constrains` alone — add server-side
   guards in `create()`/`write()` (Business Logic Placement rule). For
   sub-shape B specifically, `@api.constrains` isn't just insufficient, it's a no-op:
   `precompute=True` runs before `@api.constrains` fires (`Compute Onchange` note,
   vault: `6- Main doc/Compute Onchange.md`),
   so don't add it even as defense-in-depth — the `create()`/`write()` guard alone is
   the fix.
- [ ] Check for a one2many `context={'default_x': ...}` source even if absent from the
   subview arch (`Compute Onchange` note, vault: `6- Main doc/Compute Onchange.md`,
   "One2many context propagates
   server-side"). Verify by reading the ORM path, not the view XML.
- [ ] Write the TDD test for the *reported* case first and confirm it fails for the
   right DB-level reason (raw `NotNullViolation`, not `ValidationError`), implement,
   get green, then ask the reviewer to specifically check unfiltered section/note
   rows (A) or context-propagation correctness (B) — both caught real issues in
   past runs.
- [ ] Add a regression test for the section-row case (A) and/or the `display_type`
   defensive skip (B) once the main case is green.

## Pitfalls

- Don't pattern-match a fix from a prior occurrence onto a new report with the same
  symptom — a textually identical error on the same module has turned out to be the
  *other* sub-shape. Re-verify the actual reproduction path first.
- Don't trust the "obvious" `@api.constrains` fix for any required-field-via-
  precompute problem; the TDD test written first is what exposes that it never runs.
- A one-line fallback fix can pass all tests and still reintroduce the same crash on
  section rows — the row-shape enumeration step exists because review caught exactly
  that.

## Example instance

- 2026-07-03, sub-shape A: `sale.order.line.name` via `_compute_name`, fed by
  `dish.product_id.name` (optional) inside `Command.create` built by
  `_compute_order_lines`. Fallback `dish.product_id.name or dish.dish_name or
  dish.component_type_id.name`; review caught both loop call sites iterating
  `dish_line_ids` unfiltered over `line_section` rows — fixed with
  `.filtered(lambda d: not d.display_type)`, matching `catering_menu.py` /
  `catering_menu_cycle.py`.
- 2026-07-05, sub-shape B: identical "missing required `name`" report, same module.
  XML-RPC query showed the suspected `catering.menu` (id 135) had clean data, ruling
  out A; actual cause was manual spml/beverage/service line entry with the trigger
  field unset. Fixed via `create()`/`write()` override raising `ValidationError`.

## Relevant knowledge-base

- `Compute Onchange` note (vault: `6- Main doc/Compute Onchange.md`) — sections "precompute=True runs before
  @api.constrains", "One2many `context={'default_x': ...}` propagates server-side
  even when not in the subview arch", "`display_type` rows have a disjoint
  required-field set from normal rows".
