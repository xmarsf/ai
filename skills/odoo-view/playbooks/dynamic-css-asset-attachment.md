# Dynamic CSS via attachment in an asset bundle

Applies when: a CSS/SCSS asset must be generated at runtime from record data (e.g.
per-company theming) instead of shipped as a static file, while still loading through
a normal asset bundle.
Seeded from knowledge-base (note: Assets) — not yet validated by an orchestrated run.

Parent playbook: [implement-report](implement-report.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Write a QWeb template that renders the dynamic CSS from the driving record's
  values, per note: Assets.
- [ ] Add a Python method that renders that template and returns it base64-encoded.
- [ ] Declare an `ir.attachment` data record whose `datas` evals that method and whose
  `url` is a bundle-relative path (note: Assets).
- [ ] Register that `url` in the target assets bundle in `__manifest__.py` — pick the
  right bundle per note: Assets.
- [ ] Decide and implement the regeneration trigger: when the driving record changes,
  the attachment must be re-rendered/invalidated or the old CSS keeps serving.
- [ ] Verify in the browser that the generated rules load and change when the driving
  record changes.

## Pitfalls

- Without an explicit regeneration path, the attachment is rendered once at install
  and silently never reflects later record changes.

## Relevant knowledge-base

- note: Assets — QWeb-rendered attachment pattern (template + base64 method +
  `ir.attachment` url record + bundle registration), bundle placement rules
  (`assets_frontend` vs `assets_common`).
