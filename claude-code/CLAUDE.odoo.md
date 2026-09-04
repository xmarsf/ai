# CLAUDE.odoo.md — Odoo project guide

Drop-in memory file for Odoo addon repos. Copy or `@import` into project `CLAUDE.md`.

## First move

Any Odoo task (model, view, test, debug, migration, version question) → invoke
skill **`odoo`** first. It's a router, not a worker:

1. Reads `config/project.json` for `odoo-version` + core tree paths.
2. Missing/unresolved → refuses, tells you to run `odoo setup` (odoo-cli). No guessing.
3. States resolution: `Odoo <major> <edition> — core: <path>`.
4. Dispatches by artifact type — never do version-specific work without going through it.

No `config/project.json` yet → run `odoo setup [--dry-run]` (odoo-cli) before anything else.

## Skill dispatch table

| Task | Skill |
| --- | --- |
| Python: models, fields, constraints, security, wizards, controllers | `odoo-model` |
| XML: views, inheritance, widgets, QWeb reports, assets | `odoo-view` |
| Writing/running tests | `odoo-test` |
| Triage failing behavior, live/DB inspection | `odoo-debug` |
| Cross-major port (17/18/19), migration scripts | `odoo-upgrade` |
| Translation / Weblate `.po` round-trip | `odoo-wlc` |

## Version facts — never from memory

Before asserting any version-specific API/view/behavior claim, check the compat matrix:

```bash
odoo compat get <id> [--version MAJOR]
odoo compat list [--version MAJOR]
```

Verdicts: `removed`→error, `deprecated`/`warns`→warning, `ok`/`absent`→silent. Repo spans Odoo 17/18/19 — code correct on one major may break silently on another.

## odoo-cli — use instead of ad-hoc scripts

Repo: `/home/xmars/dev/vdx-vn/odoo-cli`, console script `odoo` (not `odoo-cli`). Missing → `python3 -m pip install -e /home/xmars/dev/vdx-vn/odoo-cli`.

| Command | Use |
| --- | --- |
| `odoo verify PATHS --root ROOT` | AST+RULES lint + git diff check. Run before calling any change done. |
| `odoo lint-rules PATHS [--check]` | Mechanical RULES.md checks only |
| `odoo compat {get,list,check,add}` | Version-verdict queries / proof validation |
| `odoo view-redundant-string PATHS [--fix]` | Strip redundant view `string=` |
| `odoo i18n {sync,export-missing,apply,import}` | Translation `.po` workflow |
| `odoo bump-manifest MANIFEST [--write]` | Bump `__manifest__.py` version |
| `odoo runtime-test --module M [--tests ...]` | pytest-odoo run, full report saved |
| `odoo module {install,update,uninstall}` | odoo-bin lifecycle ops |
| `odoo setup [--dry-run] [--force]` | Discover project layout, write `config/project.json` |

Full flags: `odoo --help` / `odoo <sub> --help`.

## Workflow

New project → `odoo setup` → invoke skill `odoo` for actual work → `odoo verify` before calling anything done.
