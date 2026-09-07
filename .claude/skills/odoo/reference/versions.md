# Odoo majors at a glance (17 / 18 / 19)

This page is a map, not an authority. Every row is an entry id in the
compatibility matrix owned by odoo-cli. Before relying on any verdict here,
resolve it for the project's version:

```bash
odoo compat get <id>                 # resolved for config/project.json's version
odoo compat get <id> --version 19    # explicit major
odoo compat list --kind view-xml     # all entries of a kind
```

Verdict vocabulary: `ok` (supported), `deprecated` (works, emits a deprecation
warning), `warns` (silently ignored with a registry log warning), `removed`
(AttributeError / hard failure), `absent` (does not exist yet). A version with
no data means **unknown** — the tooling reports unknown, never guesses, and
neither should you.

## Core layout first (affects every source lookup)

- `orm-module-layout` — 17/18: ORM lives in flat modules (`odoo/models.py`,
  `odoo/fields.py`, `odoo/api.py`). 19: package layout (`odoo/orm/`,
  `odoo/models/`, `odoo/fields/`, `odoo/api/`). Any grep into core source must
  use the per-version layout or it silently answers empty. Proofs differ per
  major by design; `odoo compat check` re-verifies them.

## Python API

| id | 17 | 18 | 19 | Replacement (when not `ok`) |
| --- | --- | --- | --- | --- |
| `name-get` | ok | removed | removed | `_compute_display_name` |
| `name-search-override` | ok | removed | removed | `_search_display_name(operator, value)` |
| `user-has-groups` | ok | removed | removed | `self.env.user.has_group(...)` / `has_groups(...)` |
| `check-access-rights` | ok | deprecated | deprecated | `check_access(operation)` / `has_access(operation)` |
| `sql-constraints` | ok | ok | warns | `models.Constraint(definition, message)` class attribute |
| `osv-expression` | ok | ok | deprecated | `odoo.fields.Domain` |
| `self-_cr` | ok | ok | deprecated | `self.env.cr` |

Note on `sql-constraints` at 19: `warns`, not `removed` — the registry logs
"no longer supported" and silently drops the constraint; the database never
sees it. `check-access-rights` is deprecated at 19, **not** removed — code
calling it still runs.

## Views / XML

| id | 17 | 18 | 19 | Replacement (when not `ok`) |
| --- | --- | --- | --- | --- |
| `view-attrs-states` | removed | removed | removed | column/attribute-level `invisible`/`readonly`/`required` expressions |
| `view-tree-tag` | ok | removed | removed | `<list>` root tag (type Selection renamed `tree`→`list` in 18) |
| `chatter-tag` | absent | ok | ok | `<chatter/>` replaces the manual div/`oe_chatter` block |

`view-attrs-states` is removed across all three majors — never write
`attrs="..."`/`states="..."`. `chatter-tag` at 17 means the `<chatter/>` tag
does not exist yet: 17 uses the manual `<div class="oe_chatter">` block.

## Edition (enterprise)

Entries carry an `edition` axis (`any` or `enterprise`); every entry listed
above is `any`. An enterprise-marked entry only resolves for projects whose
config declares `odoo_enterprise_path` — and the router's opening protocol
already refuses an enterprise project with no enterprise path. Query it
explicitly with `odoo compat get <id> --edition enterprise`.

## Hygiene

`odoo compat check` re-greps every proof against the declared local trees
(PROOF OK / LINE DRIFT / PROOF STALE / SKIPPED). It is a local gate only — CI
has no core trees. When a row here contradicts `odoo compat get`, trust the
command and update this page; when real code contradicts both, that is a new
quirk — route it through the loop in [updating.md](updating.md).
