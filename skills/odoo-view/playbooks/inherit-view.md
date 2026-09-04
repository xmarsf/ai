# Inherit / extend an existing view

Applies when: a task modifies an existing view (form/list/search/kanban) via
`inherit_id` and `<xpath>`/positional `<attribute>` edits, rather than authoring a
brand-new view from scratch.

Called by: [implement-view](implement-view.md), [implement-model](../../odoo-model/playbooks/implement-model.md)
— alternative branch; matching this condition stops/replaces the remaining parent
path.

## Usage
- used: 0 (tracking started 2026-07-13)
- last used: 2026-07-16

## Steps

- [ ] Locate the base view being inherited (`inherit_id`) and the exact node to target
  — prefer a stable `<field name="...">`/`<xpath expr="...">` anchor over a fragile
  positional index.
- [ ] Apply rule: [xml] inherited-view replacement — hide the original node with an
  `invisible` attribute, then insert the new node separately; do not use
  `position="replace"`.
- [ ] run playbook: [view-inheritance-patterns](view-inheritance-patterns.md) for the `<attribute add=.../>` merge
  mechanics (booleans merge, `context`/`domain` dicts don't) before writing the
  `<attribute>` edit itself.
- [ ] Is the underlying question really "where should this domain/readonly/required
  live at all" rather than "how do I write the XML"? → run playbook:
  [field-constraint-placement](../../odoo-model/playbooks/field-constraint-placement.md) first, then come back to write the attribute.
- [ ] Adding/changing columns, labels, ordering, or display-only formatting on a
  list/tree view? → run playbook: [one2many-list-display-columns](one2many-list-display-columns.md) if it's a one2many
  sub-list.
- [ ] Purely relabeling a field or changing its widget (no behavior change)? → run
  playbook: [relabel-field-and-widget](relabel-field-and-widget.md).
- [ ] Choosing or reconsidering which widget fits a field? → run playbook:
  [widget-usage](widget-usage.md).
- [ ] Removing a now-redundant `string=` that matches the model field's own label? →
  run playbook: [redundant-view-string-cleanup](redundant-view-string-cleanup.md).
- [ ] Does the model need two or more genuinely distinct UIs (not just one inherited
  tweak)? → run playbook: [separate-views-same-model](separate-views-same-model.md) instead of layering more
  `<xpath>` edits onto one view.
- [ ] Replacing an `act_window target="new"` popup flow with a custom in-page dialog?
  → run playbook: [form-view-dialog-replacement](form-view-dialog-replacement.md).
- [ ] Nesting a dialog inside another dialog? → run playbook: [form-dialog-nesting](form-dialog-nesting.md)
  (avoid nested `target="new"`).
- [ ] List footer needs a total/average? → run playbook: [list-field-aggregation](list-field-aggregation.md).
- [ ] Any label/string touched → run playbook: the **odoo-wlc** skill (translation round-trip).
- [ ] XML fails to parse, validate, install, or upgrade → run playbook:
  [xml-debug](../../odoo-debug/playbooks/xml-debug.md), then return here for rendered-view verification.
- [ ] View-only → **module-update path**; view carries **business behavior** → **TDD
  path** for that logic.

## Pitfalls

- If the requested change still appears absent after a successful module update,
  inspect the rendered view and the inherited xpath target before changing code.
- `<attribute add=.../>` and view-vs-Python domain fallback pitfalls are owned by
  [view-inheritance-patterns.md](view-inheritance-patterns.md) (called above) — don't restate them here.

## Example instance

- 2026-07-10: `connecting_flight_id` domain declared only on the Python field failed
  to restrict the view's search widget — fixed by adding the domain at the XML level
  (see [add-sibling-domain-many2one-field.md](../../odoo-model/playbooks/add-sibling-domain-many2one-field.md), and [view-inheritance-patterns.md](view-inheritance-patterns.md) for
  the general mechanics this instance surfaced).

## Relevant knowledge-base

- Load-bearing facts for this shape live behind [view-inheritance-patterns.md](view-inheritance-patterns.md)'s own
  pointers — add a note here only if a run finds one specific to the broader
  inherit-view task shape itself.
