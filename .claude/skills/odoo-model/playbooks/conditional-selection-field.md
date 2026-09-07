# conditional-selection-field

Applies when a Selection field's valid options must narrow based on a sibling field
on the same record (e.g. `condition` options depend on `surcharge_type`), and the
codebase already has a `dynamic_selection` widget pattern elsewhere to copy.

Parent playbook: [implement-field](implement-field.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Grep the target field's name across the whole addons tree first — this pattern
   is usually copy-pasted per module (one model shape vs another), so an existing
   implementation almost certainly exists to mirror rather than invent.
- [ ] Compute the comma-separated allowed selection keys from the sibling field.
- [ ] Add `_onchange_<sibling_field>` that resets the constrained field to `False` when
   the sibling changes (prevents a stale invalid value from surviving).
- [ ] Wire **dynamic_selection** with its `available_field` and keep that carrier field
  in the view.
- [ ] Confirm the owning module depends on `account`, which provides the widget.

## Pitfalls

- Do not hand-roll a widget before checking **dynamic_selection**.
- Field-name collisions: verify the sibling field's own selection *keys* match what
  the compute field emits — don't assume two existing implementations of this pattern
  in the same codebase use the same key spellings for the same concept; always check
  the target model's own selection list before reusing another model's key set.

## Example instance

- a surcharge model in one addon — original pattern, its carrier field name carried
  a source typo (don't propagate it to new code).
- a quotation line model + its views file in another addon — second instance, named
  correctly. Its selection keys (`'day,night'`) didn't match the first model's
  (`'daytime,nighttime'`) despite representing the same concept — confirmed by
  reading each target model's own selection list rather than assuming
  interchangeability.

## Relevant knowledge-base

- note: Odoo Glossary — dynamic_selection.
