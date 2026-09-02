# odoo-cli: which command for which job

All subcommands resolve the project from `config/project.json`
(`odoo-version` major + edition, core trees, db, rc, python). Unresolvable →
they exit non-zero with `run 'odoo setup' first` — that refusal is strict by
design; fix the config, don't work around it. Exact flags: `odoo <command> --help`.

## Setup / config

- `odoo setup` — first time in a project: discovers layout and writes
  `config/project.json` (`odoo-version`, `odoo_community_path`,
  `odoo_enterprise_path`, rc, db, python). `--dry-run` previews;
  `--force` overwrites; `--conf` pins an exact odoo.conf; `--weblate-project`
  stores the Weblate slug.
  Caution: a write **replaces** the file with discovered fields only — check
  the dry-run's `missing` list first; keys an old config had that discovery
  does not find (db, venv python, addons_dir, ...) would be dropped.

## Pre-done checks (run before calling module work complete)

- `odoo verify PATHS --root ROOT` — AST + RULES lint + `git diff --check` in
  one shot. The default "done" gate for any module change.
- `odoo lint-rules PATHS [--check]` — mechanically-checkable rule items,
  **version-gated**: each rule carries a matrix id and fires only when the
  resolved major's verdict is `deprecated`/`warns`/`removed`. `--check` exits 1
  on hits (CI-style gating).
- `odoo view-redundant-string PATHS [--fix] [--check]` — detect/fix view
  `string=` that redundantly matches the field definition.

## Version facts (compat matrix)

- `odoo compat get <id>` — one entry, JSON, resolved for the project's
  version/edition. Exit 1 unknown id; verdict `unknown` when a version has no
  data. Use before asserting any version-specific fact.
- `odoo compat list [--kind python-api|view-xml|orm-layout|behavior]
  [--status candidate|confirmed]` — filtered listing; load only what a task needs.
- `odoo compat check` — re-greps every proof against the declared core trees;
  reports PROOF OK / LINE DRIFT / PROOF STALE / SKIPPED, exit 1 on STALE.
  Local gate only (CI has no core trees).
- `odoo compat add --id ... --proof N=odoo/...:"PATTERN" ...` — write-back of a
  quirk found during work; refuses a proof that doesn't match a declared tree;
  writes `status: candidate`. Never hand-edit the matrix YAML.
  See [updating.md](updating.md) for the full loop.

## Run / test

- `odoo runtime-test --module M [M...]` — update module and run pytest-odoo
  against the config DB; short summary on stdout, full report (raw failures)
  always saved to `output_file`. `--tests` picks files; `--init install|update`
  controls the `-i`/`-u` pass; pass several `--module` names to run them in one
  pytest call.
- `odoo module install|update|uninstall M...` — lifecycle against the config DB.
- `odoo start [-i M] [-u M]` — run the server.
- `odoo shell [--code CODE | SCRIPT]` — REPL or non-interactive script inside
  the registry; first tool for live-object questions.

## Other

- `odoo i18n sync|export-missing|apply|import` — module `.po` mechanics.
  The translation workflow itself belongs to the `odoo-wlc` skill.
- `odoo bump-manifest MANIFEST [--part patch|minor] [--write]` — dry-run report
  by default.
- `odoo search view ...` — ir.ui.view families by model/menu/action.
- `odoo graph [--model M]` — method-level call graph via the live registry's
  real `_inherit` order.
