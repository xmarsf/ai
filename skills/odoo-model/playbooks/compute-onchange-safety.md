# Compute & onchange field safety patterns

Applies when: the planned diff adds or edits a compute/onchange whose value must live-update while a form is open, must be submitted from a readonly/invisible field, or posts messages/activities.

Called by: [implement-model](implement-model.md), [implement-automation](implement-automation.md)

## Usage
- used: 0
- last used: 2026-07-10

## Steps
- [ ] Live non-stored compute → include its field in the view; see `note: Compute Onchange`.
- [ ] Submitted readonly/invisible computed value → `force_save`; see `note: XML View - Field Attributes & Readonly Domain`.
- [ ] Compute side effect during form onchange → guard unsaved `NewId`; see `note: ORM Core`.
- [ ] apply rule: [python] never put business logic inside `@api.onchange` — Business Logic Placement rule: compute/onchange is for form UX, not persistence

## Relevant knowledge-base

- note: Compute Onchange — `on_change="1"` trigger mechanics, why a `store=False`
  compute needs its own field in the view.
- note: XML View - Field Attributes & Readonly Domain — `force_save` submission
  semantics.
- note: ORM Core — `NewId` truthiness/comparison behavior.
