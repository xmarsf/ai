---
name: odoo-model
description: >-
  Use when creating or editing Odoo Python model artifacts: model classes and
  _inherit extensions, fields, compute/onchange, SQL and Python constraints,
  ACL/record-rule security, TransientModel wizards, HTTP controllers,
  ir.cron/ir.actions.server/base.automation automation, mail templates and
  activities. Triggers: any change under a module's models/, wizard/,
  controllers/, or security/ files.
---

# odoo-model — Odoo Python model artifacts

Python-side artifact work in an Odoo addon. XML/view work belongs to the
**odoo-view** skill; triage of already-observed failures to **odoo-debug**;
test authoring/running to **odoo-test**; cross-major porting to **odoo-upgrade**.

## Before anything else

Read `config/project.json` at the project root and follow the five-step opening
protocol in the **odoo** router skill ([../odoo/SKILL.md](../odoo/SKILL.md)): missing/null
`odoo-version`, or null/absent `odoo_community_path` (plus
`odoo_enterprise_path` for the enterprise edition) → stop and tell the user to
run `odoo setup`. **No fallback.** If you reached this skill directly (no
router), still resolve the version first under the same rules, and state
`Odoo <major> <edition> — core: <odoo_community_path>` in your first output
line (add `— enterprise: <odoo_enterprise_path>` when the edition is
enterprise).

Never assert a version-specific API fact from memory. Before claiming "in this
version X works like Y", check `odoo compat get <id>` (known quirk) or
`odoo compat list --kind python-api`.

## Playbook routing (lazy-loaded — read only the one routed, never bulk-read)

| Playbook | Read it when |
|---|---|
| [implement-model](playbooks/implement-model.md) | any model-level task — the parent that routes all children below |
| [create-model](playbooks/create-model.md) | brand-new model identity from scratch |
| [inherit-model](playbooks/inherit-model.md) | extend a model defined elsewhere via `_inherit` |
| [implement-field](playbooks/implement-field.md) | adding/changing a field, any ttype |
| [field-constraint-placement](playbooks/field-constraint-placement.md) | domain/readonly/required: Python kwarg vs view attribute |
| [compute-onchange-safety](playbooks/compute-onchange-safety.md) | live-updating computes, `force_save`, `NewId` guards |
| [conditional-selection-field](playbooks/conditional-selection-field.md) | selection options narrowed by a sibling field |
| [add-active-field-archive](playbooks/add-active-field-archive.md) | standard Odoo archive/soft-delete via `active` |
| [add-sibling-domain-many2one-field](playbooks/add-sibling-domain-many2one-field.md) | new M2O list column filtered by sibling fields |
| [multihop-domain-relay-field](playbooks/multihop-domain-relay-field.md) | view domain needs a multi-hop relation value |
| [missing-required-field-fallback](playbooks/missing-required-field-fallback.md) | required line field populated by a stored compute (`NotNullViolation`) |
| [merge-submodel-into-shared-model](playbooks/merge-submodel-into-shared-model.md) | fold a generic/wrong submodel into an existing sibling model |
| [shared-line-model-second-parent](playbooks/shared-line-model-second-parent.md) | line model gains a second optional parent link |
| [simplify-line-submodel](playbooks/simplify-line-submodel.md) | strip an over-engineered line submodel back to plain fields |
| [implement-security-rule](playbooks/implement-security-rule.md) | ACLs, `ir.rule` record rules, groups, `check_company` |
| [implement-wizard](playbooks/implement-wizard.md) | `TransientModel` + `target="new"` dialog |
| [implement-automation](playbooks/implement-automation.md) | `ir.cron` / `ir.actions.server` / `base.automation` |
| [implement-notification](playbooks/implement-notification.md) | `mail.template`, `message_post`, `activity_schedule` |
| [mail-activity-deduping](playbooks/mail-activity-deduping.md) | activities from stored computes without duplicates |
| [implement-controller](playbooks/implement-controller.md) | `@http.route` endpoints (json / portal / webhook) |
| [controller-qweb-overrides](playbooks/controller-qweb-overrides.md) | override a controller's QWeb render context |

## Hard rules

- **Parent precedence:** when several playbooks match, run the most specific
  parent (`implement-model`, `implement-field`, `inherit-model`) and take the
  others as its children — every child's "Parent playbook" link returns you to
  the parent step you left.
- A new concrete model always gets `implement-security-rule`; wizards live
  under `wizard/`, never `models/`.
- SQL constraints: per-version form via `compat:sql-constraints`
  (`models.Constraint` class attribute vs `_sql_constraints`) — confirm with
  `odoo compat get sql-constraints`, don't guess.
- `tracking=` only on `mail.thread` models (directly or via mixin).
- Verification gate: declarative schema → module-update path; business logic →
  TDD path via the **odoo-test** skill (`odoo runtime-test`).
- Label/string changes route translation work to the **odoo-wlc** skill.
- Automation tiebreaker: this skill owns the **Python side** of automation
  (server-action code, model-level automation logic); **odoo-view** owns the
  XML data-record authoring (`data/*.xml` record definitions) — a
  `base.automation`/`ir.actions.server` change splits that way, not to one skill.
- Rename/refactor of a model that **already holds data** in the same major
  routes to **odoo-upgrade** (a migration script is needed); routine model
  edits stay here.
