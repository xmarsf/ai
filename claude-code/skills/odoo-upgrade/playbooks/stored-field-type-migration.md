# stored-field-type-migration

Applies when: changing a stored field's `ttype` on an existing model (e.g.
`Selection` → `Many2one`) where production databases may already hold data in
the old column, especially when the field is also written by a stored compute
elsewhere in the codebase.

Parent playbook: [implement-field](../../odoo-model/playbooks/implement-field.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Grep every reader/writer of the field across all addons (Python vals dicts,
   `@api.depends`, views, `.po` selection msgids) before touching anything — a
   field used only for display is a different risk profile than one fed by a
   second, independent compute path.
- [ ] If the field is a stored compute output with multiple `@api.depends` entries,
   grep the compute body for each dependency to rule out a **dead depends** (listed
   but never read — can wipe data another code path wrote). Split into independent
   methods scoped to the fields each dependency actually feeds if found. (note: check
   knowledge-base for an existing topic on dead-depends recompute risk; file one if
   missing.)
- [ ] Change the field definition (`Selection` → `Many2one(comodel)` etc.).
- [ ] Run playbook: [write-version-migration-script](write-version-migration-script.md)
   for **pre- / post- / end-migrate**, guards, and rename/backfill ordering; resume
   here with one canonical old-value → new-record mapping.
- [ ] **Target can be a Many2many, not just Many2one** — same rename-then-backfill
   dance, landing in a `<model>_<field>_rel` table instead of a column via a single
   `INSERT INTO rel_table SELECT id, old_column FROM table WHERE old_column IS NOT
   NULL` in post-migrate. If the application-level change also merges what used to
   be N rows sharing a dedup key into 1 row with the union of their tag values, do
   that merge in the compute/write path that builds the row (dedup-key → in-flight
   `Command.create` vals dict, appending `Command.link(id)` per match), not in the
   migration.
- [ ] Prune now-orphaned `Selection` `msgid` blocks from `.po` files (search for
   `selection__<model>__<field>__*`). Run playbook:
   the **odoo-wlc** skill (manifest-and-translation-hygiene flow)
   for the shared-msgid discipline (keep `field_description`, only strip the `#:`
   reference line when a msgid is shared) and the version-bump/pylint close-out.
- [ ] Update any Python code that previously built the field's value through a
   lossy string map to instead assign the real referenced record's id
   directly (this is usually the actual point of the fix — the old Selection
   was collapsing distinct values into a catch-all).
- [ ] Persistent tests: (a) round-trip the new field type end-to-end from
   whatever upstream flow populates it, comparing against the real recordset
   (not a string); (b) if a dead-depends bug was found in step 2, add a
   regression test that edits the unrelated dependency field and asserts the
   fixed field's data survives; (c) if dedup logic keyed on the old lossy
   value, add a test proving two records that used to collapse to one now
   produce two.

## Pitfalls

- Don't assume `@api.depends` entries are all load-bearing — grep the method
  body for each one.
- Keep migration mechanics in [write-version-migration-script](write-version-migration-script.md), not duplicated here.

## Relevant knowledge-base

- `Migrate scripts` note (vault: `6- Main doc/Migrate scripts.md`) — "pre-migrate / init_models / post-migrate ordering",
  source-cited against `odoo/modules/loading.py`. Verify it still matches the
  active repo's Odoo version rather than assuming it's evergreen.

## Example instance

- 2026-07-07 — two `passenger_class` fields on related item-price/service models:
  `Selection` → `Many2one('service.class')`
  in one addon, plus a genuinely independent dead-depends bug in
  the owning model's price compute (`tool_quota_ids`/
  `material_quota_ids` never used in the body, wiping synced
  `passenger_class` data on any quota edit). Both fixed together per user
  request after initial investigation surfaced the second bug as the more
  load-bearing one. Migration: `migrations/<bumped-version-1>/`. Verified
  ordering against `odoo/modules/loading.py:load_module_graph`.

- 2026-07-08 — the item-price field again: `Many2one('service.class')`
  → `Many2many`, driven by a UI requirement (one price line
  per product instead of one per (class, product) pair, classes shown as
  comma-separated tags). Dedup key in the command-collector changed from
  `(service_class.id, product.id)` to `product.id` alone; merged the
  `Command.create` vals dict per the new sub-step above instead of writing a
  second migration-side merge. Migration:
  `migrations/<bumped-version-2>/`. The same-named `passenger_class` on
  a different tab/model with its own independent Many2one was correctly left
  untouched — verified via full-repo grep before assuming both fields needed
  the same treatment just because they shared a name.
