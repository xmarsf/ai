# Inherit QWeb report templates

Applies when: inheriting a QWeb report template and targeting an element by CSS class.

Parent playbook: [add-custom-qweb-pdf-report](add-custom-qweb-pdf-report.md) — returning sub-step; resume the next parent step.

## Usage
- used: 0
- last used: 2026-07-10

## Steps
- [ ] In inheritance XPath, use **hasclass()** for class-membership matching.
- [ ] Keep runtime `t-if` expressions separate; `hasclass()` is an XPath helper.

## Pitfalls
- Do not copy XPath syntax into a QWeb `t-if` expression.

## Relevant knowledge-base

- note: Odoo Glossary — `hasclass()`.
- source: `odoo/addons/base/models/ir_ui_view.py:_hasclass`.
