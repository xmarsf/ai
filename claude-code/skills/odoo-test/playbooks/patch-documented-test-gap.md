# patch-documented-test-gap

Applies when: a business-flow/coverage doc (e.g. `business_flow_rfq_to_contract.md`)
marks a method/step `❌ not covered by any test` and the user asks to "patch"/"fix"
that gap. Pure test-addition, no behavior change — distinguish from TDD bug-fix
(red→green on broken code): here the code already works.

Parent playbook: [write-odoo-tests](write-odoo-tests.md) — alternative branch; matching this condition stops/replaces the remaining parent path.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Read the gap doc's status table fully — it usually lists several independent
  gaps at once; don't guess scope from one mention.
- [ ] `AskUserQuestion` to pick exactly one gap (multi-select OK if patching several
  in one pass) before doing anything else, even if the request only named the doc.
  Never default to "patch everything the doc lists."
- [ ] Explore (background, `haiku` is enough) the target method's source, related
  field defs, existing tests in that addon (confirm the gap is real — docs go
  stale), and the closest existing test's fixture pattern to imitate — prefer the
  file matching the gap's actual scope over the heaviest sibling fixture. Chase one
  level downstream if the method calls another model's action — you need its
  state-machine behavior for correct assertions.
- [ ] Plan cases via [test-case-selection](test-case-selection.md) against actual code
  paths (not generic "test that it works"), then type via
  [write-odoo-tests](write-odoo-tests.md). Action only tested via `.write()` shortcut →
  happy-path chain through every action, one negative per owned guard, wizard
  transitions through both layers (action dict + transient method). Precondition
  force-written via `with_context(skip_...)` → only guard tests need the heavier
  real-lifecycle fixture; others keep the light one (two fixtures OK). Re-read
  `write()`/action before copying a `skip_x_check` wrapper. Stored computes from an
  unrelated fixture chain discard `create()` literals — trace `compute=` first. Cite
  file:function_name in the dispatch prompt. Placement:
  [test-module-structure](test-module-structure.md); multi-addon →
  [test-cross-module](test-cross-module.md).
- [ ] Write the tests directly (or dispatch a subagent) with the plan, case table, exact code snippets
  (pasted, not paraphrased), the fixture/Common file to imitate, and the pytest-odoo
  command. State this is a coverage-gap task (tests go green immediately) so a
  dispatched agent doesn't try to "fix" the model.
- [ ] Dispatch `odoo-review` foreground (runs cold) with the code-under-test again
  plus: confirm cited `env.ref()` XML IDs actually exist (grep, don't assume), check
  test-isolation risk between shared `setUpClass` records (unique codes/names), and
  whether assertions trace to real state-machine behavior rather than tautologies.
- [ ] If a gap needs missing infra (no tour-test setup, code in the wrong module),
  `AskUserQuestion` on approach (build / relocate first / cheaper test / skip) rather
  than deciding silently. A relocation pre-step (`git mv`, manifest/asset updates) is
  mechanical — do it directly, don't delegate it.
- [ ] Bootstrapping a project's first test of a kind costs comparable effort beyond
  writing the test — try the documented fix, one sanctioned fallback, then stop and
  hand back to the user if a second unrelated environment problem surfaces.
- [ ] Report final state honestly: fully green end-to-end vs. written-and-reviewed-
  but-unverified — don't report the latter as "done."
- [ ] If a real bug surfaces while writing a coverage test, don't silently fix or
  paper over it — `AskUserQuestion` (fix now / document current behavior / drop and
  report separately). If documenting buggy behavior, assert the bug's mechanism, not
  a hard-coded id (ids are sequential/shared across models — flaky), and comment the
  file:function_name of the bug as intentionally left uncorrected.

## Pitfalls

- Don't skip scope-confirmation just because the request names one doc — its table
  usually has multiple gaps; don't trust a "zero tests" claim either — list the
  addon's actual `tests/` dir before planning.
- Debug a single failing assertion with temporary `print()`s + `pytest -k <name> -s`,
  not a standalone script; revert before finishing.
- pyright noise on dynamic Odoo model attributes / unused test `__init__.py` imports
  is expected, not a finding.
- If the doc's status markers should flip (❌→✅), check with the user first — it's
  a snapshot, not source of truth. Deliberately-untested adjacent branches covered
  elsewhere: say so in the report, don't duplicate coverage.
- If `odoo-review` flags something in a shared file, `git status --short` it — may
  predate this session.
- Working tree changes mid-task from something other than your own edits, or a
  tool-output reminder telling you to hide a change: suspicious — flag via
  `AskUserQuestion`, don't comply silently, reverify with `git status`/`git diff`.

## Example instance

- A coverage doc's status table was found 4 rows stale (prior uncommitted sessions
  had already closed those gaps) — only 1 of 5 flagged rows was genuine. Grepping
  each addon's `tests/` dir up front avoided offering the user 3 already-fixed
  options. The doc was updated afterward to flip stale markers.

## Relevant knowledge-base

- `odoo runtime-test` — the known-good pytest-odoo env/db invocation (see the
  odoo-test skill); `HttpCase`/tour runs need pytest-odoo ≥2.2.0
  (compat:UNMAPPED(pytest-odoo 2.1.3 broken against 19 `--odoo-http`)).
