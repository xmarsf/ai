# Relay field for a multi-hop view domain

Applies when: a view (often a one2many subview) needs a domain filtered by a value only
reachable through two or more Many2one hops from the current record — symptom is an
`InvalidDomainError` on the dotted path, or silently empty results.
Seeded from knowledge-base (note: Odoo domain) — not yet validated by an orchestrated
run.

Parent playbook: [implement-field](implement-field.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Confirm the shape: the failing domain dots through more than one Many2one hop
  (view domains support at most one hop — note: Odoo domain).
- [ ] Add a relay compute field on the model the view sits on, depending on the full
  dotted path; decide store vs non-store — client-side domain use alone needs no
  store (note: Odoo domain).
- [ ] Place the relay field in the parent form/view as `invisible="1"` (note: XML
  View — client only reads fields present in the view).
- [ ] Rewrite the view domain to reference the relay field with a single hop.
- [ ] Verify in both create (record not yet saved) and edit flows — the relay must
  have a value before the filtered field is touched.

## Pitfalls

- The failure can be silent (empty candidate list) rather than an error, depending on
  where the domain is declared — verify the filtering actually applies, not just that
  no error is raised.

## Relevant knowledge-base

- note: Odoo domain — one-hop limit for dotted paths in view domains, relay-field
  workaround, `parent.` prefix scope in sub-line domains.
