# merge-submodel-into-shared-model

Applies when: the ask is to stop representing one kind of business data via a
generic/wrong submodel (often `sale.order.line` with a `line_type` discriminator
carrying pricing fields it shouldn't have) and instead represent it as
domain-filtered rows of an *existing sibling model* that already serves a
structurally similar purpose (e.g. two different "quantity per seat class" concepts
sharing one line model), rather than inventing a brand-new model.

Parent playbook: [implement-model](implement-model.md) — alternative branch; matching this condition stops/replaces the remaining parent path.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] **Check whether the target model's populating field is a full-rebuild stored
   compute** (`store=True, compute=...` doing `Command.clear()` then an unconditional
   rebuild). If so, a parallel write path into the same field gets wiped on the next
   recompute — extend the existing compute's `@api.depends` and body instead so one
   method owns 100% of that field's rows (mechanism: not yet in the knowledge-base
   vault, see note below).
- [ ] **Prove the multi-hop reverse `@api.depends` path works before relying on it.**
   If the compute needs to react to a field several relation-hops away, check whether
   a *shallower* version of the same hop pattern already exists and is tested in that
   same method (e.g. it already depends on a compute one hop closer, itself fed by
   the deeper field). If so, the deeper chain is safe by the same mechanism — don't
   just assume; find the existing shallower proof first (mechanism: not yet in the
   knowledge-base vault, see note below).
- [ ] **Convert `related=` fields the destination model needs to set directly to
   plain stored fields**, when the merged-in data can't derive the value through the
   original relation chain. Add an explicit stored discriminator field (boolean,
   related to the distinguishing flag on the linked record, `store=True`) directly
   on the line model so views can filter on it without a dotted-path domain
   (mechanism: x2many list widgets and two-hop domains — not yet in the
   knowledge-base vault, see note below).
- [ ] **Write a post-migrate backfill whenever a `related=` field becomes a plain
   stored field on a model fed by another model's stored compute.** The module
   upgrade adds the new column but does NOT backfill historical rows — only new
   compute runs populate it. Follow this module's existing migration pattern (see
   `migrations/<version>/pre-migrate.py` for column-rename precedent) but as a
   `post-migrate.py` that calls the compute method directly on the owning
   recordset (`env[<model>].search([...])._compute_<field>()`), inside
   `api.Environment(cr, SUPERUSER_ID, {})`. Bump `__manifest__.py` version to match
   the new migration folder.
- [ ] **When picking an existing O2M field for a "manually-created line survives"
   regression test**, check whether that field is itself a self-clearing stored
   compute (wipes manual rows on next recompute) before using it — prefer a plain,
   non-compute O2M sibling on the same model if one exists.
- [ ] **Grep the whole module (not just the one field) for the discriminator value
   being removed** (e.g. a `line_type`/Selection value used only by the removed
   rows) — delete the Selection option and any option-only-used-by-it fields
   entirely rather than leaving them dead.
- [ ] run playbook: the **odoo-wlc** skill (manifest-and-translation-hygiene flow) — covers the version bump,
   `.po` shared-msgid discipline, and pylint pass. Expect `unused-argument` on
   migration scripts' `version` parameter from the pylint step; this is accepted
   project-wide (every existing `pre-migrate.py` triggers it too), not a real finding.

## Pitfalls

- Don't design the merge model as an afterthought bolt-on field on the destination
  line model without checking whether pricing/invoicing code elsewhere assumed the
  *old* model (e.g. `sale.order.line`) contributed to `amount_total` — confirm with
  the user this is an intentional behavior change (it usually is, since the whole
  point of the merge is dropping pricing), then grep for other consumers rather than
  assuming none exist.
- Don't leave a new test that only asserts "does not raise" for a silent-skip
  branch — if the DB already seeds real data that makes the branch unreachable
  (e.g. `service.class` codes seeded for every `*_class` value in a real dev DB),
  the assertion never actually exercises the skip path. Patch the lookup map/class
  attribute in-process for that one test instead of assuming a fixture gap exists.

## Example instance

- 2026-07-08 — a quantity-only, no-product input line model was being synced into
  `sale.order.line` rows with a `line_type` discriminator
  and no `product_id`, tripping a product-required constraint. Redesigned to
  aggregate into an existing sibling line model (already backing a related
  per-class quantity concept) via a new stored related boolean,
  folded into the parent's existing full-rebuild compute.
  Removed the ad hoc sync method and its lookup map entirely — the compute's
  `@api.depends` now covers the sync automatically. Added
  `migrations/<bumped-version>/post-migrate.py` to backfill the new discriminator
  columns
  for existing orders. `.pylintrc` at repo root, not inside the addon tree.

## Relevant knowledge-base

- No direct topic yet — the reverse multi-hop `@api.depends` trigger mechanism and
  the x2many-domain-can't-traverse-Many2one limitation would be good candidates for
  an `knowledge-base` note if this pattern recurs; not yet written there.
