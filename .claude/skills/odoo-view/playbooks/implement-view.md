# Implement a view

Applies when: a task needs a form/list/search/kanban view, `ir.actions.act_window`, or
menu entry for a model — either authored from scratch or as a modification of an
existing view, and must first decide which.

Entry point: [SKILL.md](../SKILL.md)
Called by: [implement-model](../../odoo-model/playbooks/implement-model.md)

## Usage
- used: 0 (tracking started 2026-07-16)
- last used: 2026-07-16

## Steps

- [ ] Modifying an existing view via `inherit_id`/`<xpath>`/positional `<attribute>`
  edits, rather than authoring a new one? → run playbook:
  [inherit-view](inherit-view.md) and stop this checklist.
- [ ] Otherwise, author only the views the task actually needs (form for detail, list for
  browsing, search for filtering) — don't scaffold a kanban/calendar/graph view nobody
  asked for.
- [ ] Form view: order fields to match how a user actually fills the record, group
  related fields into the same `<group>`, and only mark a field `required`/`readonly`
  in XML when that state is view-context-specific — a field's own model-level
  `required=True` already covers the general case.
- [ ] List view: pick the columns a list actually needs for scanning/sorting, not every
  field on the model; needs a footer total/average → run playbook:
  [list-field-aggregation](list-field-aggregation.md).
- [ ] Search view: add the filters/group-bys the model's own use cases call for; avoid
  duplicating a filter the default search already provides via `search_default_`
  context keys.
- [ ] Choosing a widget for a given field type → run playbook:
  [widget-usage](widget-usage.md).
- [ ] Wire the `ir.actions.act_window` (`res_model`, `view_mode`, default `context`) and
  the menu item it hangs off — place it under the module's own existing menu root
  unless the task explicitly asks for a new one.
- [ ] Model needs two or more genuinely distinct UIs from day one (not a later
  addition) → run playbook: [separate-views-same-model](separate-views-same-model.md)
  instead of cramming both into one view.
- [ ] Any label/string on the view/action/menu → run playbook:
  the **odoo-wlc** skill (translation round-trip).
- [ ] New model's access rows not yet created → run playbook:
  [implement-security-rule](../../odoo-model/playbooks/implement-security-rule.md) before the view is reachable
  by any non-admin user.
- [ ] XML fails to parse, validate, install, or upgrade → run playbook:
  [xml-debug](../../odoo-debug/playbooks/xml-debug.md), then return here for rendered-view verification.
- [ ] View-only → **module-update path**; view exposes new **business behavior**
  (a button, a compute-backed field) → **TDD path** for that logic.

## Pitfalls

- Scaffolding every view type "to be complete" instead of the ones the task's own use
  cases require adds surface area with no behavior behind it.
- Forgetting the access rows before wiring the menu leaves a broken/forbidden entry
  point for any non-admin user who clicks it.

## Example instance

- (seed entry — fill in with the first run that authors a view through this playbook:
  which view types were actually needed and why.)

## Relevant knowledge-base

- No dedicated vault note yet for fresh-authoring layout conventions — the
  inherit/xpath mechanics live behind [inherit-view](inherit-view.md)'s own
  [view-inheritance-patterns](view-inheritance-patterns.md) pointer, not here. Write
  one back after the first orchestrated run through this playbook.
