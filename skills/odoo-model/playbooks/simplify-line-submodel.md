# simplify-line-submodel

Applies when: a one2many line sub-model has grown an over-engineered selection flow
(e.g. a multi-hop lookup→derived-value chain with onchanges and a computed domain
field) that no longer matches the simple functional spec, and the ask is to strip it
back to a plain picker field + a couple of directly-editable fields, in a specific
column order.

Parent playbook: [inherit-model](inherit-model.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Find the current FS doc for the feature (functional-spec markdown/xlsx converted
   to md) and read the exact target column list/order — it's often much simpler than
   what's in code, meaning the code accreted complexity the FS never asked for.
- [ ] Grep the whole owning module (not just the one model file) for every field name
   you're about to remove, across `*.py` and `*.xml`. If nothing outside the one
   view references them, removal is contained — much lower risk.
- [ ] Look at a sibling line sub-model in the same module for the established
   plain-field pattern (e.g. a required Many2one picker field with `related=`
   readonly fields for its display/unit attributes plus a required Monetary amount).
   Mirroring an existing sibling's shape keeps the module internally consistent
   instead of inventing a new one.
- [ ] Because the interpretation ("just add a field" vs "also rip out the old
   relation flow") changes the model shape, ask the user with AskUserQuestion before
   touching code — don't guess silently on a fork this size.
- [ ] After removing fields, grep the module again for the *dependency* that only
   existed to back those removed fields (e.g. a manifest `depends` entry for a
   now-unused module). Do NOT drop it reflexively — first grep the whole module for
   any other use of models from that dependency (mixins like `mail.thread`, other
   model refs). If genuinely unused, it's tempting to swap in a "more correct"
   dependency, but don't guess a replacement without tracing the actual transitive
   requirement graph — that's scope creep with real breakage risk. Prefer leaving the
   existing `depends` entry alone unless you've fully traced why it's there.
- [ ] run playbook: the **odoo-wlc** skill (manifest-and-translation-hygiene flow) — version bump and pylint pass
   for the touched model file.

## Pitfalls

- Don't reflexively swap a now-unused module dependency for a "more correct" one —
  trace the transitive requirement graph fully before touching `depends`, or leave
  it alone.

## Example instance

- 2026-07-05: simplified a beverage line sub-model (a
  quota→quota-item→derived-product chain with onchanges and a computed domain field)
  down to a plain `product_id`/`name`/`uom_id`/`unit_price` shape mirrored from the
  sibling supplement line model.

## Relevant knowledge-base

No direct topic — process only.
