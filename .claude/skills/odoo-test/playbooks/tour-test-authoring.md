# Author a JS tour test

Applies when: the test-type decision (playbook: write-odoo-tests, type table) has
already landed on "JS tour + HttpCase" — a multi-step real-browser flow (wizard,
drag-drop, widget JS behavior) that `Form`/ORM tests can't express. This playbook is
the authoring procedure; it does not re-make case selection or the type decision.
Seeded from knowledge-base (note: Tour Test) — not yet validated by an orchestrated
run.

Parent playbook: [write-odoo-tests](write-odoo-tests.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Locate (or create) the addon's tour directory under `static/tests/tours/` and an
  existing sibling tour to imitate, per note: Tour Test.
- [ ] Register the tour under **web.assets_tests**; add the manifest bundle entry if needed.
- [ ] Verify each step's trigger selector against the real rendered DOM (run the flow
  once in a browser/dev instance) — don't write selectors from memory of the widget
  markup.
- [ ] Drive it from `HttpCase.start_tour` with `post_install / -at_install`.
- [ ] Assert the resulting DB state after `start_tour` returns — a tour that merely
  finishes proves clicks worked, not that the business effect happened.
- [ ] Run it once end-to-end through the repo's pytest-odoo setup with `--odoo-http`;
  if the environment can't confirm the tour runs within
  budget, say so explicitly in the report and hand off per write-odoo-tests Step 3 —
  don't burn turns retrying a hang.

## Pitfalls

- Keep bundle and tag mechanics in `note: Tour Test`; this playbook owns only the sequence.

## Relevant knowledge-base

- note: Tour Test — tour file shape and registration API, `web.assets_tests`
  requirement, `HttpCase.start_tour` signature, tagging convention, known hang failure
  mode, file:function_name citations and a real sibling tour example.
