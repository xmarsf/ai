---
name: odoo-view
description: >-
  Use when creating or editing Odoo XML artifacts: view arch
  (form/list/kanban/search), inherited views and xpath edits, widgets,
  res.config.settings sections, asset bundles, QWeb/PDF report templates, and
  ir.actions/data records in XML. Triggers: any change under a module's
  views/ or data/ XML files.
---

# odoo-view — Odoo XML artifacts

XML-side artifact work in an Odoo addon: views, inheritance, widgets, settings,
assets, QWeb reports. Python model work belongs to the **odoo-model** skill;
triage of XML load/validation failures to **odoo-debug** (`xml-debug`);
translation round-trip to the **odoo-wlc** skill.

## Before anything else

Read `config/project.json` at the project root and follow the five-step opening
protocol in the **odoo** router skill (`skills/odoo/SKILL.md`): missing/null
`odoo-version`, or null/absent `odoo_community_path` (plus
`odoo_enterprise_path` for the enterprise edition) → stop and tell the user to
run `odoo setup`. **No fallback.** If you reached this skill directly (no
router), still resolve the version first under the same rules, and state
`"<major> <edition>"` in your first output line.

Never assert a version-specific XML fact from memory. Before claiming "in this
version the arch syntax is X", check `odoo compat get <id>` or
`odoo compat list --kind view-xml`.

## Playbook routing (lazy-loaded — read only the one routed, never bulk-read)

| Playbook | Read it when |
|---|---|
| [implement-view](playbooks/implement-view.md) | new/changed form/list/search/kanban + `act_window` + menu — the parent |
| [inherit-view](playbooks/inherit-view.md) | modify an existing view via `inherit_id`/xpath |
| [view-inheritance-patterns](playbooks/view-inheritance-patterns.md) | `<attribute add>` merge mechanics, xpath pitfalls |
| [widget-usage](playbooks/widget-usage.md) | which widget fits a field type |
| [relabel-field-and-widget](playbooks/relabel-field-and-widget.md) | pure label/widget/`.po` display change, no logic |
| [one2many-list-display-columns](playbooks/one2many-list-display-columns.md) | columns of a one2many sub-list |
| [list-field-aggregation](playbooks/list-field-aggregation.md) | list footer totals/averages |
| [form-view-dialog-replacement](playbooks/form-view-dialog-replacement.md) | replace a `target="new"` popup with an in-page dialog |
| [form-dialog-nesting](playbooks/form-dialog-nesting.md) | dialog inside another dialog |
| [separate-views-same-model](playbooks/separate-views-same-model.md) | model needs 2+ genuinely distinct UIs |
| [create-settings-page](playbooks/create-settings-page.md) | new `res.config.settings` section end-to-end |
| [settings-sections](playbooks/settings-sections.md) | `o_settings_container` DOM inside a settings block |
| [redundant-view-string-cleanup](playbooks/redundant-view-string-cleanup.md) | remove `string=` duplicating the field label |
| [dynamic-css-asset-attachment](playbooks/dynamic-css-asset-attachment.md) | CSS/SCSS asset generated from record data |
| [implement-report](playbooks/implement-report.md) | printable output — QWeb-PDF vs XLSX decision |
| [add-custom-qweb-pdf-report](playbooks/add-custom-qweb-pdf-report.md) | `ir.actions.report` + template + `_get_report_values` |
| [qweb-report-templates](playbooks/qweb-report-templates.md) | reusable QWeb report template shapes |

## Hard rules

- Inherited views: hide the original node (`invisible` attribute) and insert
  the new node separately — **never `position="replace"`** (`odoo verify`
  flags it).
- No legacy `attrs`/`states` syntax (compat:view-attrs-states — removed in
  every supported major): use attribute-level `invisible`/`readonly`/`required`
  expressions.
- `<tree>` → `<list>` from 18 on (compat:view-tree-tag) — confirm with
  `odoo compat get view-tree-tag` before writing arch.
- Redundant `string=` cleanup runs through `odoo view-redundant-string
  --check`, not by eye.
- View-only change → module-update path; view exposes new business behavior
  (button, compute-backed field) → TDD path via the **odoo-test** skill.
- XML fails to parse/validate/install → **odoo-debug** (`xml-debug`), then
  return here for rendered-view verification.
