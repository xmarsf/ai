# test-failure-log-triage

Applies when: the user pastes a raw pytest/odoo test-run log with multiple
independent failing/erroring tests and asks to "fix the bug(s)".

Parent playbook: [write-odoo-tests](../../odoo-test/playbooks/write-odoo-tests.md) — alternative branch; matching this condition stops/replaces the remaining parent path.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Split the log into one failure per traceback — prefer the structured JSON
  report `odoo runtime-test --output` already saves (one row per failing test) as
  the work unit; for an arbitrary pasted log, split it by hand into one traceback
  per failure and record the same fields (`node_id`, `exception_type`,
  `file`/`func`, module) per row.
- [ ] `git status`/`git diff` before touching code; diff each modified file against
  its failing test — some may already be fixed by uncommitted WIP.
- [ ] Classify each failure independently: app bug / wrong test assertion-fixture /
  environment-schema issue.
- [ ] Confirm the log's db name against `config/project.json` (the db `odoo
  runtime-test` uses) — do not reuse the log's db name as-is.
- [ ] "Missing table"/"invalid field" during test setup → check
  `ir_module_module.state` vs `to_regclass` before assuming a code bug; if
  installed-but-missing-table, run `-u`, don't patch code.
- [ ] Failing `-u` migration script → confirm with user before patching; reuse
  existing existence-check idiom (e.g. `_column_exists`).
- [ ] After code fixes, re-run the failing-test set via `odoo runtime-test` to
  confirm, unless all failures are pure environment/schema with no code fix.
- [ ] After fixing a state-guard, re-run the whole affected test file, not just the
  prompting test.
- [ ] Grep for `_name` of the changed model in other addons; re-run their test
  suites too.
- [ ] Two modules' tests assert contradictory behavior → `AskUserQuestion`, don't
  resolve silently.
- [ ] Review subagent names a regression → run that specific test before trusting
  the claim.
- [ ] Unrelated pre-existing failure, untouched by your diff → note in report, leave
  out of scope.

## Pitfalls

- One bug per traceback — don't lump a multi-traceback log into one root cause.
- Don't narrow a `state not in (...)` guard using only the named test(s).
- Don't silently pick a db name from a pasted CI log.

## Relevant knowledge-base

- `odoo runtime-test` — the known-good pytest-odoo env/db invocation (see the
  odoo-test skill); its `--output` report is the structured failure source.
