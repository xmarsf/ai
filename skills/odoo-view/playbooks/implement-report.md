# Implement a printable report

Applies when: a model needs a new or changed printable output — QWeb-PDF, or an
XLSX/spreadsheet export — bound to it via a print action or menu item.

Entry point: [SKILL.md](../SKILL.md)
Called by: [implement-model](../../odoo-model/playbooks/implement-model.md)

## Usage
- used: 0 (tracking started 2026-07-13)
- last used: n/a

## Steps

- [ ] Decide the report shape first — QWeb-PDF (document layout, print/preview) vs.
  XLSX (tabular export, no print/preview). They use different base infrastructure;
  don't default to QWeb-PDF just because it's the more common case.
- [ ] QWeb-PDF → run playbook: [add-custom-qweb-pdf-report](add-custom-qweb-pdf-report.md) for the full
  `ir.actions.report` + template + `_get_report_values` sequence.
- [ ] XLSX/spreadsheet export → base on `report.report_xlsx.abstract` (or the
  project's existing xlsx report pattern if one already exists in a neighboring
  module) — grep for an existing `report_xlsx` inherit in the codebase before writing
  one from scratch.
- [ ] Needs custom render-context overrides at the controller layer rather than
  `_get_report_values`? → run playbook: [controller-qweb-overrides](../../odoo-model/playbooks/controller-qweb-overrides.md).
- [ ] Needs a generated CSS/SCSS asset from record data (report-specific styling)? →
  run playbook: [dynamic-css-asset-attachment](dynamic-css-asset-attachment.md).
- [ ] Any label/header/column title in the report → run playbook: the **odoo-wlc** skill (translation round-trip).
- [ ] Verify with edge-shaped data (empty lines, long text, missing optional fields) —
  report layout bugs rarely show on the happy-path record.

## Pitfalls

- A shared `report_name`/binding can leak the print action into unwanted menus/view
  types if not scoped — check where the binding surfaces after adding it.

## Example instance

- (seed entry — fill in with the first run that picks between QWeb-PDF and XLSX at
  the first checklist item.)

## Relevant knowledge-base

- `Report` note (vault: `6- Main doc/Report.md`) — `ir.actions.report` fields, QWeb layout wrappers,
  `_get_report_values` contract, `_prepare_html`/`_run_wkhtmltopdf` pipeline.
