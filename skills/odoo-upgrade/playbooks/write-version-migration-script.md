# Write a version migration script

Applies when: a module version bump needs a pre/post/end-migrate hook — a column type
change, a data backfill, or a schema/data repair that the ORM's automatic schema sync
cannot do safely on its own.
Seeded from knowledge-base (notes: Migration data, Migrate scripts) — not yet validated
by an orchestrated run.

Called by: [implement-model](../../odoo-model/playbooks/implement-model.md), [stored-field-type-migration](stored-field-type-migration.md), [implement-migration](implement-migration.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Bump the module version in `__manifest__.py`; create (or reuse)
  `migrations/<new version>/` matching that exact version string.
- [ ] Pick the script phase relative to `init_models`: `pre-` (before schema sync),
  `post-` (after), or `end-` (after all modules) — per note: Migration data.
- [ ] Name the file with a hyphenated prefix (`pre-<name>.py`, not `pre_<name>.py`) —
  the loader only picks up hyphenated prefixes (note: Migration data).
- [ ] For a column type change: rename the old column away in the `pre-` script so the
  ORM creates the new column fresh, then backfill and drop the renamed column in the
  `post-` script — never let the ORM auto-cast in place (note: Migrate scripts).
- [ ] Write `migrate(cr, version)` with that exact signature — init hooks take a
  single `env` (compat:init-hooks-env-signature: pre/post init hooks take `env` on
  17/18/19 — not a 19 change; migration scripts keep `migrate(cr, version)`) which
  applies to init
  hooks only, not migration scripts (note: Migrate
  scripts). Build an env inside if ORM access is needed.
- [ ] Guard xml-id lookups with `raise_if_not_found=False` — the record may not exist
  on every database the migration runs against.
- [ ] Verify the version-skip upgrade path: a database several versions behind must
  still execute the intermediate migration files in order (note: Migration data).
- [ ] Before renaming/removing a field or model, `git log -p`/`git blame` the target to
  check whether it was itself already renamed once before, then grep every addon (not
  just the one being migrated) for the old name — a dependent module's own field/domain
  can still reference the pre-migration name and silently break or go orphaned if the
  migration only updates the owning module.

## Pitfalls

- An underscore in the filename prefix (`pre_migrate.py`) silently does nothing — the
  script is never picked up and the migration "succeeds" without running.
- Doing the type change in one phase (instead of pre-rename + post-backfill) hands the
  conversion to the ORM's auto-cast, which can fail or corrupt data on non-trivial
  type pairs.
- A field/model rename that only updates its owning module: dependent modules
  referencing the old name via `related=`, domains, or `_inherit` fields go orphaned
  or break, and this is easy to miss because `git log` on the owning module alone
  won't surface it — the break shows up later as an unrelated-looking test failure or
  runtime error in the dependent module.

## Relevant knowledge-base

- note: Migration data — phase semantics (`pre-`/`post-`/`end-`), file naming, version
  directory matching, version-skip execution order.
- note: Migrate scripts — `migrate(cr, version)` signature, env construction, the
  init-hook `env` signature (see compat:init-hooks-env-signature above) and why it does not
  apply here, column-type-change
  rename/backfill pattern.
