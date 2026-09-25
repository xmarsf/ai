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
| `odoo deps MODULES [--upstream\|--downstream\|--both]` | Static dependency closure from manifests; default downstream (dependents), dependency-first order |
| `odoo runtime-test --module M [--tests ...]` | pytest-odoo run, full report saved |
| `odoo module {install,update,uninstall}` | odoo-bin lifecycle ops |
| `odoo setup [--dry-run] [--force]` | Discover project layout, write `config/project.json` |

Full flags: `odoo --help` / `odoo <sub> --help`.

## Workflow

New project → `odoo setup` → invoke skill `odoo` for actual work → `odoo verify` before calling anything done.

## Critical execution rules

### Odoo tests and module validation

Do not run Odoo tests, module upgrades, or Odoo validation commands directly in the current Bash or Python environment.

Delegate all Odoo validation to an Antigravity (`agy`) agent.

#### Step 1 — Determine the validation scope

Never validate only the module you edited. Before delegating, build the full validation scope from the dependency graph of the changed modules.

1. List every module touched by the change (from the diff, not from memory):

   ```bash
   { git diff --name-only <base>; git ls-files --others --exclude-standard; } | grep '^addons/' | cut -d/ -f2 | sort -u
   ```

   `git diff <base>` covers committed and uncommitted changes; `git ls-files --others` adds new untracked files.

2. Resolve the changed modules plus all their transitive dependents with `odoo deps` (odoo-cli). Downstream is the default direction:

   ```bash
   odoo deps <module_1>,<module_2>
   ```

   The JSON `modules` field is the validation scope, already ordered dependency-first. Use it as-is; do not rebuild it by grepping manifests.

3. Check the rest of the report before trusting the scope:
   * `unknown_modules` non-empty → a changed module was not found under the resolved `addons_path`. Fix the name or pass `--addons-path`; do not drop it silently.
   * `manifest_errors` → those addons were skipped from the graph. Fix or report them; their dependents may be missing from the scope.
   * `dependency_cycle` → report it; ordering among those modules is not guaranteed.
   * No `addons_path` resolved → run `odoo setup` or pass `--addons-path`.

Include dependents even when the change looks local. These changes break dependent modules before they break the module you edited:

* Overridden or renamed methods and changed method signatures.
* Renamed, removed, or retyped fields.
* Changed, renamed, or removed XML external IDs and inherited views.
* New or changed `ir.model.access.csv` entries, record rules, and groups.
* Changed `_inherit`, `_name`, or model removal.
* Changed manifest `depends` or data-file load order.

#### Step 2 — Select the test cases to run

Pick the test cases from the actual change, not by running every suite in the scope by default. For each module in the scope, read its `tests/` directory and choose:

1. **Changed modules** — tests that exercise the changed code:
   * Test files/classes for the changed models (`_name`/`_inherit`), methods, fields, wizards, controllers, and reports.
   * Tests that reference changed XML IDs, views, security groups, or record rules.
   * New or edited test files in the diff — always included.
2. **Dependent modules** — tests that touch the changed surface from outside. Search each dependent's `tests/` for the changed model names, field names, method names, and XML IDs:

   ```bash
   grep -rlE "<model_name>|<field_or_method>|<module>\.<xml_id>" addons/<dependent>/tests/
   ```

   Also include tests for any dependent code that overrides or `super()`-calls a changed method.
3. **Widen to the full module suite** when the change cannot be mapped to specific cases: manifest `depends`/data-file changes, `_name`/`_inherit` changes, model removal, shared mixins or base helpers, `ir.model.access.csv`/record-rule changes, or `setUp`/`setUpClass` fixtures used by many tests.
4. **No matching tests** for a module in the scope → that module goes to the upgrade group (see below), not silently dropped.

Express the selection with `odoo runtime-test` flags:

* `--tests addons/<m>/tests` — full suite of a module (required for full-suite modules once any `--tests` is given, since `--tests` disables auto-discovery).
* `--tests addons/<m>/tests/test_x.py` — whole file.
* `--tests addons/<m>/tests/test_x.py::TestClass` or `::TestClass::test_case` — one class or case.
* `-k 'TestInvoice or test_refund'` — select by name across the modules.

Record the selection per module with a one-line reason (e.g. `sale_custom: tests/test_order.py::TestOrderConfirm — overrides action_confirm`). The final report must list it.

#### Step 3 — Delegate the run

Pass the whole scope to a single delegated run. `odoo runtime-test` accepts multiple `--module` arguments, so init and test them together instead of one call per module. Include the selected tests from Step 2.

```bash
agy --dangerously-skip-permissions --model "gemini-pro-agent" --prompt "Run tests for Odoo modules <module_1> <module_2> ... using 'odoo runtime-test' from odoo-cli, passing every module in one invocation with repeated --module flags, in dependency order, and restricting the run to these selected tests: <--tests ... / -k ... from Step 2>. These modules are the changed modules plus all of their transitive dependents. Analyze the output and provide a concise summary of the test results, failures, and relevant file locations."
```

After the command finishes:

1. Read the agent output.
2. Identify the actual cause of any failure.
3. Apply the necessary code changes.
4. Run validation again through `agy` when needed.

If the scope is a mix of modules with and without selected tests, split it into two groups and run both delegated calls: the test prompt above for the modules with selected tests, and the upgrade prompt below for the modules without.

When a module in the scope has no automated tests, or none matched the change in Step 2, instruct the agent to run a module upgrade for it instead:

```bash
agy --dangerously-skip-permissions --model "gemini-pro-agent" --prompt "Upgrade Odoo modules <module_1> <module_2> ... using odoo-cli, in dependency order, to detect registry, Python import, XML, data loading, access-control, and view validation errors. Analyze the output and provide a concise summary with relevant file locations."
```

Never report that a change is validated unless the delegated test or upgrade completed successfully for every module in the scope. If part of the scope was not run, say which modules were skipped and why.

### Ruff linting

The repository uses Ruff.

The configuration file is:

```text
addons/ruff.toml
```

Important configuration details:

* Line length: `180`
* Python target: `py310`
* The file contains per-addon exclusions.
* The configuration is under `addons/`, not the repository root.

Do not run Ruff directly in the current environment.

Do not apply Ruff fixes directly with local tools.

Delegate every Ruff lint and fix operation to an `agy` agent:

```bash
agy --model "gemini-pro-agent" --prompt "Run 'ruff check --fix' on <module_or_path> using config addons/ruff.toml. Apply safe fixes automatically. Report all remaining issues with file path, line number, and Ruff rule code. Identify issues that are fixable only with '--unsafe-fixes', but DO NOT apply unsafe fixes. Summarize the safe changes that were applied and the remaining items requiring manual review."
```

Safe fixes may be applied by the delegated agent.

Unsafe fixes must not be applied automatically. Review each unsafe-fixable issue manually and only change it after confirming that behavior is preserved.

## Stress-testing plans

Before committing to a non-trivial implementation plan or design decision, invoke the `grilling` skill to interview the user and surface hidden assumptions and tradeoffs, rather than proceeding on an unstated assumption.

## File locations

- Save written plan files to `addons/docs/plans/`.
- Save temporary or disposable files and folders to `tmp/`. Clean them up once the implementation or usage they supported is finished.

## Restricted files

Never touch `*.po` and `*.pot` files. No create, edit, delete. Translation files managed exclusively through `odoo i18n` workflow (odoo-cli), not by agent.

## Architecture and module ownership

Before implementing a feature, identify the module that owns the behavior.

Do not place logic in a shared or lower-level module merely because it is convenient. Respect the existing dependency direction and avoid introducing circular dependencies.

## Implementation workflow

Before making changes:

1. Read the target module's `__manifest__.py`.
2. Identify its dependencies and dependent modules.
3. Search for existing models, fields, views, actions, security rules, and overrides related to the requested behavior.
4. Identify the correct owning module.
5. Check whether the same behavior exists in another production variant.
6. Avoid duplicating an existing helper, mixin, service, or workflow.

After making changes:

1. Review the complete diff.
2. Check imports, inheritance, method signatures, and module dependencies.
3. Delegate Ruff validation through `agy`.
4. Build the validation scope with `odoo deps`: changed modules plus all transitive dependents (see "Odoo tests and module validation").
5. Select the test cases affected by the change for each module in the scope.
6. Delegate the selected tests, or a module upgrade where no tests match, for that whole scope through `agy`.
7. Report validation results accurately.
