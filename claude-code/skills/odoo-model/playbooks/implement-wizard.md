# Implement a wizard (TransientModel)

Applies when: a task adds or changes a modal confirm/input dialog that performs an
action on one or more target records — a `models.TransientModel` bound to a
`target="new"` action.

Entry point: [SKILL.md](../SKILL.md)
Called by: [implement-model](implement-model.md)

## Usage
- used: 2 (tracking started 2026-07-13)
- last used: 2026-07-16

## Steps

- [ ] **Placement:** put the TransientModel Python file under the owning addon’s
  `wizard/` or `wizards/` package (and import it from there). Do **not** drop
  wizards into `models/` — that package is for persistent models only.
- [ ] Define the `TransientModel` identity: `_name` + `_description`.
- [ ] Prefill with a field `default=` or `default_get()`; preserve `super()` behavior.
- [ ] Choose typed relational targets for one model; use `res_model` + `res_id` only
  for genuinely polymorphic targets.
- [ ] For each field → run playbook: [implement-field](implement-field.md).
- [ ] Confirm method: `ensure_one()`, perform the operation, then close or return the
  next action; share one worker across multiple confirm buttons. x2many writes use
  `Command.update` / `Command.create` / … — never wholesale reassignment of the O2M.
- [ ] Build the modal form/footer and a `target=new` action; add action bindings only
  when the wizard belongs in an Actions menu. Register the view XML under
  `wizard/` (or `views/` with a wizard-named file) and list it in the manifest.
- [ ] Any access restriction on who can open/use it → run playbook:
  [implement-security-rule](implement-security-rule.md).
- [ ] Any label/string on the wizard or its view → run playbook: the **odoo-wlc** skill (translation round-trip).

## Pitfalls

- Use `fields.Command` semantics for x2many defaults; do not decode raw command tuples inline.
- Putting a `TransientModel` under `models/` breaks standard Odoo layout expectations
  and harness/quality checks that look for `wizard*/**/*.py`.

## Example instance

- (seed entry — fill in with the first run that creates a wizard through this
  playbook: target model(s), default strategy chosen, confirm-button shape.)

## Relevant knowledge-base

- `Odoo Wizards` note (vault: `6- Main doc/Odoo Wizards.md`)
