# Implement a data/version migration

Applies when: a task needs a one-off data backfill or bulk import against existing
schema, and must first decide the right mechanism — a `post_init_hook`, a
`migrations/<version>/` script, or a plain data file — before writing any of them.
Not for a stored field's `ttype` change alone (that's
[stored-field-type-migration](stored-field-type-migration.md)), though that playbook
routes here for the script-writing step.

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 1 (tracking started 2026-07-16)
- last used: 2026-07-21

## Steps

- [ ] One-time backfill that only needs to run once, at this module's own
  install/upgrade (no schema change, no repeat on later upgrades) → a `post_init_hook`
  in `__manifest__.py` is usually simpler than a versioned migration script.
- [ ] Needs to run against every database as it upgrades through a specific module
  version (schema/data repair the ORM's automatic sync can't do safely) → run
  playbook: [write-version-migration-script](write-version-migration-script.md).
- [ ] Bulk import of reference/seed data from an external file → prefer a plain XML/CSV
  data file (with `noupdate` set appropriately) over an ad hoc Python script, unless the
  transformation genuinely needs procedural logic a data file can't express.
- [ ] Whichever mechanism is chosen, verify it is idempotent — guard with an existence
  check — since upgrade paths can retry a script/hook that partially ran.
- [ ] Migration touches a field/model that may have been renamed before → cross-module
  reference check (see write-version-migration-script's pitfall on this) before
  assuming the owning module is the only one affected.

## Pitfalls

- Reaching for a versioned migration script when a `post_init_hook` would do: adds
  version-directory bookkeeping for something that only ever needs to run once, at this
  module's own install.
- Writing a bulk-import script for data a plain XML/CSV data file could load — loses
  the framework's own load/update semantics for no benefit.

## Example instance

- (seed entry — fill in with the first run that picks a mechanism through this
  playbook: which of the three was chosen and why.)

## Relevant knowledge-base

- note: Migration data — phase semantics, file naming, version-skip execution order
  (shared with [write-version-migration-script](write-version-migration-script.md)).
