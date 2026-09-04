# Relabel field / change widget / adjust i18n

Applies when a request is purely about column labels, display widgets
(Float→Monetary, many2one display format via context), or translation
text in the module's `.po` catalogs — no new business logic, no schema/data
migration concern.

Parent playbook: [inherit-view](inherit-view.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Skip full plan/tests/review ceremony scaling — this is inherently a small,
   testable-by-inspection change with no new behavior to assert; no test dispatch
   needed. Still run `odoo-review` at the end.
- [ ] Before touching XML for a relabel task, read the `XML View` note (vault:
   `6- Main doc/XML View.md`) → "Field label
   tự động lấy từ Python `string=`" — it determines whether XML needs
   touching at all here.
- [ ] "Make widget consistent with sibling monetary fields" (Float→Monetary):
   check whether a `currency_id`-type field already exists on the model/view
   first (see the `Odoo Fields` note, vault: `6- Main doc/Odoo Fields.md`, for the
   underlying-column/migration reasoning).
- [ ] "Show `[Code] Name` for a many2one column": check the `Odoo Fields` note →
   "Context-driven `display_name`" before writing a new override.
- [ ] run playbook: the **odoo-wlc** skill (manifest-and-translation-hygiene flow) — covers the shared-msgid
   grep/decouple, `.po` split, and pylint steps that apply to every string this task
   touches.

## Pitfalls

- The shared-`msgid` decoupling pitfall and its worked example live in
  the **odoo-wlc** skill (manifest-and-translation-hygiene flow) (called above) — don't restate them here,
  read that skill's Pitfalls/Example instance sections instead.

## Relevant knowledge-base

- `Odoo Fields` note (vault: `6- Main doc/Odoo Fields.md`) — context-driven
  `display_name` pattern, `show_code_name` example.
- `XML View` note (vault: `6- Main doc/XML View.md`) — field label auto-derivation
  from Python `string=`.
