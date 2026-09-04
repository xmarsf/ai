# Add a custom QWeb PDF report

Applies when: a model needs a new printable QWeb-PDF report — a print action bound to
the model, a QWeb template, and optionally custom render context or PDF layout control.
Seeded from knowledge-base (note: Report) — not yet validated by an orchestrated run.

Parent playbook: [implement-report](implement-report.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Define the `ir.actions.report` record: `report_name` (module.template_xmlid),
  target model, binding, and paper format — per note: Report.
- [ ] Create the QWeb template under the xml id the `report_name` points to, using the
  standard layout wrappers from the note. When inheriting a template and targeting a
  CSS class, run playbook: [qweb-report-templates](qweb-report-templates.md).
- [ ] If the template needs data beyond `docs`, add a report model overriding
  `_get_report_values` — don't compute report-only values on the business model.
- [ ] If custom HTML-to-PDF handling is needed, route through `_prepare_html` before
  `_run_wkhtmltopdf` and keep header/footer heights fixed (note: Report).
- [ ] Check where the print binding surfaces: if a shared `report_name`/binding leaks
  the entry into unwanted view types or menus, restrict it (the note covers the
  `get_views`-level restriction).
- [ ] Verify: render the PDF for a record with edge-shaped data (empty lines, long
  text) — layout bugs don't show on the happy-path record.

## Relevant knowledge-base

- `Report` note (vault: `6- Main doc/Report.md`) — `ir.actions.report` fields, QWeb template layout wrappers,
  `_get_report_values` contract, `_prepare_html`/`_run_wkhtmltopdf` pipeline,
  print-binding visibility control.
