# Implement a model

Applies when: a task needs model-level work — (a) new concrete model / `TransientModel`
identity vs extending an existing one, (b) non-trivial behavior change on an existing
model — including a **bug fix, extension, or override of existing pure-Python business
logic** on a model method (method overrides, archive/soft-delete, state machine,
create/write guards), or (c) multi-artifact model work that spans host model + child
shapes (e.g. new field on an existing model plus a bulk wizard). Prefer this parent
over peer-matching `implement-field` / `implement-wizard` alone when those are
reachable as its children (see SKILL **parent precedence**). A bug fix or logic
extension that touches no field/view/security artifact still routes here for its
`_inherit`/`super()` steps — see [inherit-model](inherit-model.md).

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 4 (tracking started 2026-07-13)
- last used: 2026-07-17

## Steps

- [ ] Existing identity → `_inherit`; delegated identity → `_inherits`; otherwise `_name`.
- [ ] Is this actually a `res.config.settings` section? → run playbook:  [create-settings-page](../../odoo-view/playbooks/create-settings-page.md) and stop this checklist.
- [ ] Is this a technical rename of an existing model/table? → run playbook:  [model-technical-rename](../../odoo-upgrade/playbooks/model-technical-rename.md) and stop this checklist.
- [ ] Is the task replacing a generic/wrong submodel with an existing sibling model?
  → run playbook:  [merge-submodel-into-shared-model](merge-submodel-into-shared-model.md) and stop  this checklist.
- [ ] Editing the **owning** model's own class in place (same module already defines
  `_name` there — e.g. a bug fix or new branch inside an existing method on a model
  this addon owns)? → **no branch**; that's not an `_inherit` extension, stay in this
  checklist's own steps (super()/batch-semantics step below still applies if the
  method being touched calls `super()`).
- [ ] Extending a model defined **elsewhere** (core, community addon, or another
  addon module) via `_inherit` from this module? → branch to run playbook:
  [inherit-model](inherit-model.md), then return to the next parent step.
- [ ] Otherwise (no existing identity to patch/extend at all), branch to run
  playbook: [create-model](create-model.md), then return to the next parent step.
- [ ] For each new or changed field → run playbook:  [implement-field](implement-field.md).
- [ ] Needs archive/unarchive instead of hard `unlink`? → run playbook:
  [add-active-field-archive](add-active-field-archive.md). **If TDD is planned
  (step 3 before this implement step):** expand that playbook **before**
  [test-case-selection](../../odoo-test/playbooks/test-case-selection.md) so owned cases (esp. create-path
  when state-gated) land in the first tdd dispatch — see
  [write-odoo-tests](../../odoo-test/playbooks/write-odoo-tests.md) feature-case-inputs step.
- [ ] Overrides a method → preserve the `super()` chain and return value, keep batch
  semantics, and prefer an existing hook over the whole caller. Ground edge cases in
  `Odoo Extensible Inheritance`.
- [ ] Adds or changes a `type="object"` state-transition button? → run playbook:  [action-button-double-trigger-guard](../../odoo-debug/playbooks/action-button-double-trigger-guard.md).
- [ ] Adds or changes a `compute`/`onchange` that live-updates a form, writes through
  readonly/invisible fields, or posts mail/activities? → run playbook:  [compute-onchange-safety](compute-onchange-safety.md).
- [ ] Posts activities/messages as a side effect? → run playbook:  [mail-activity-deduping](mail-activity-deduping.md).
- [ ] Needs user-facing views? For an existing model/view, run playbook:
  [inherit-view](../../odoo-view/playbooks/inherit-view.md). For a new model/view authored from scratch, run
  playbook: [implement-view](../../odoo-view/playbooks/implement-view.md).
- [ ] Security: for a new concrete model, always run playbook:  [implement-security-rule](implement-security-rule.md); for an existing model, run
  it when access or visibility changes.
- [ ] Needs a printable document? → run playbook:  [implement-report](../../odoo-view/playbooks/implement-report.md).
- [ ] Needs a user-facing action wizard? → run playbook:  [implement-wizard](implement-wizard.md).
- [ ] Existing-data transformation not already routed by a child playbook? → run
  playbook: [write-version-migration-script](../../odoo-upgrade/playbooks/write-version-migration-script.md).
- [ ] Any new or changed `string=`/label → run playbook:  the **odoo-wlc** skill (translation round-trip).

## Pitfalls

- Check the `_inherit` chain before creating a table.
- Skipping `super()` on one branch silently breaks other overrides in the MRO.
- Looping and calling `super().create(vals)` per record breaks multi-record batch
  semantics.

## Example instance

- (seed entry — fill in with the first orchestrated run that exercises this routing
  decision, including the selected branch and the evidence used.)

## Relevant knowledge-base

- note: Odoo Model — `_name`/`_inherit`/`_inherits` semantics, table creation.
- `Odoo Extensible Inheritance` note (vault: `6- Main doc/Odoo Extensible Inheritance.md`)
