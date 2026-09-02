# Implement access control (ACL / record rules / groups)

Applies when: a task needs a new `ir.model.access.csv` row, a new/changed `ir.rule`
record rule, a new security group, or a `check_company=True` field — any change to who
can see/do what.

Entry point: [SKILL.md](../SKILL.md)
Called by: [implement-model](implement-model.md), [implement-wizard](implement-wizard.md), [implement-controller](implement-controller.md), [implement-view](../../odoo-view/playbooks/implement-view.md), [xml-debug](../../odoo-debug/playbooks/xml-debug.md)

## Usage
- used: 1 (tracking started 2026-07-13)
- last used: 2026-07-16

## Steps

- [ ] Model CRUD → `ir.model.access`; row filtering → `ir.rule`.
- [ ] Choose **global rule vs group rule** deliberately.
- [ ] Company-bound relation → `check_company=True` and `_check_company_auto`.
- [ ] UI visibility → `groups=`; add ACL/rules when the data itself needs protection.
- [ ] Role hierarchy → `res.groups` + `implied_ids`.
- [ ] Privilege escalation → review and minimize `sudo()` scope.
- [ ] Verify as a representative non-admin user, including allowed and denied cases.

## Pitfalls

- Do not use `sudo()` to mask an ACL/rule design gap; see `note: Odoo Security`.

## Example instance

- (seed entry — fill in with the first run that adds/changes an ACL or record rule
  through this playbook.)

## Relevant knowledge-base

- `Odoo Security` note (vault: `6- Main doc/Odoo Security.md`)
