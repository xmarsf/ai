---
name: odoo-upgrade
description: >-
  Use when porting an Odoo addon across major versions (17/18/19) or writing
  version migration scripts: the compat port checklist from `odoo compat`,
  migrations/<version>/ pre/post scripts, stored-field ttype changes, and
  model technical renames. Triggers: "port to 19", a version bump that needs
  data migration, a rename of a model that already holds data.
---

# odoo-upgrade — cross-major porting and migration scripts

Port an addon between majors (17/18/19) and write the migration scripts that
move its data. Single-version artifact work belongs to **odoo-model** /
**odoo-view**; this skill owns the version delta.

## Before anything else

Read `config/project.json` at the project root and follow the five-step opening
protocol in the **odoo** router skill ([../odoo/SKILL.md](../odoo/SKILL.md)): missing/null
`odoo-version`, or null/absent `odoo_community_path` (plus
`odoo_enterprise_path` for the enterprise edition) → stop and tell the user to
run `odoo setup`. **No fallback.** If you reached this skill directly (no
router), still resolve the version first under the same rules, and state
`Odoo <major> <edition> — core: <odoo_community_path>` in your first output
line (add `— enterprise: <odoo_enterprise_path>` when the edition is
enterprise).

Everything below consumes the matrix through `odoo compat` — never from
memory.

## Port checklist (matrix-driven)

Given source major S and target major T:

1. `odoo compat list --version S` and `odoo compat list --version T` (JSON).
2. Severity order: `ok` < `deprecated` < `warns` < `removed`. An entry whose
   verdict worsens from S to T becomes one checklist line:
   `- <id> — <replacement>`.
3. Always add every `kind: orm-layout` entry whose per-version proof file path
   differs between S and T (verdicts may be `ok` on both sides while the path
   still moves — e.g. `odoo/models.py` → `odoo/orm/`). It changes every
   core-source lookup in the port.
4. An entry `absent` in S but `ok` in T is a new capability — list separately
   as optional modernization, not a blocker.
5. An `unknown` verdict (version key missing from the entry) goes in a
   "verify manually against the target tree" section — never guessed.
6. Work the checklist into the port plan: each line is either a mechanical
   rewrite (via the odoo-model / odoo-view skills) or a migration-script task
   (below).

### Worked example: 17 → 19 (verified against the seed matrix, 2026-09-02)

Checklist lines (verdict worsens, or orm-layout path moves):

| id | 17 → 19 | replacement |
|---|---|---|
| name-get | ok → removed | `_compute_display_name` |
| name-search-override | ok → removed | `_search_display_name(operator, value)` |
| view-tree-tag | ok → removed | `<list>` instead of `<tree>` |
| sql-constraints | ok → warns | `models.Constraint(...)` class attribute |
| user-has-groups | ok → removed | `self.env.user.has_group(...)` / `has_groups(...)` |
| check-access-rights | ok → deprecated | `check_access(operation)` / `has_access(operation)` |
| osv-expression | ok → deprecated | `odoo.fields.Domain` |
| self-_cr | ok → deprecated | `self.env.cr` |
| orm-module-layout | path moves | core lookups: `odoo/models.py` → `odoo/orm/` per version |

Not blockers: `view-attrs-states` (already `removed` in 17 — no delta);
`chatter-tag` (absent → ok: new `<chatter/>` capability, optional
modernization).

## Migration-script conventions

- Directory: `migrations/<exact bumped module version>/` — the version string
  must match `__manifest__.py` after the bump.
- Phases: `pre-migrate.py` (before schema sync), `post-migrate.py` (after),
  `end-migrate.py` (after all modules).
- Filename prefix uses a **hyphen** (`pre-foo.py`); an underscore prefix is a
  silent no-op — the script never runs.
- Signature: `def migrate(cr, version)` — build an `env` inside if ORM access
  is needed. (Init hooks take a single `env` on 17/18/19 — compat:init-hooks-env-signature;
  migration scripts keep `migrate(cr, version)`.)
- Stored-field ttype changes: never let the ORM auto-cast — rename the old
  column away in `pre-`, backfill and drop in `post-`.
- Every script idempotent: guard with existence checks; upgrade paths retry.
- `odoo compat get orm-module-layout` tells you where core source lives for
  the target major before you grep any core path.

## Playbook routing (lazy-loaded — read only the one routed, never bulk-read)

| Playbook | Read it when |
|---|---|
| [implement-migration](playbooks/implement-migration.md) | choose the mechanism: `post_init_hook` vs `migrations/` script vs data file |
| [write-version-migration-script](playbooks/write-version-migration-script.md) | author a pre/post/end-migrate script |
| [stored-field-type-migration](playbooks/stored-field-type-migration.md) | change a stored field's `ttype` with data on disk |
| [model-technical-rename](playbooks/model-technical-rename.md) | rename `_name`/table while preserving data |

## Hard rules

- The port checklist comes from `odoo compat list` output — never from memory,
  never from a stale doc.
- A module rename or field rename migrates dependent addons too — grep every
  addon for the old name, not just the owner.
- Rename/refactor of a model that **already holds data** in the same major
  routes here (a migration script is needed); routine model edits stay with
  **odoo-model**.
- After the port: run `odoo verify` (version-gated lint), then
  `odoo runtime-test --init update` for the touched modules.
