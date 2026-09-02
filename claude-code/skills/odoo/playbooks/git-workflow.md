# git-workflow

Applies when: finishing a unit of Odoo dev work in the project repo — review the diff
and commit. **Do not push or open/refresh the upstream MR unless the user explicitly
asks in this session.**

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 5 (tracking started 2026-07-10)
- last used: 2026-07-17

## Repo layout

Run all git commands from the project repo root (the checkout holding the addons).

| Remote     | Role                                  |
|------------|---------------------------------------|
| `origin`   | Your fork — working branch lives here |
| `upstream` | Team repo — MR target                 |

## Steps

- [ ] `git status`, `git diff --stat` from the repo root first. Any bulk `git add -A`
  step stages everything dirty — stash/commit unrelated in-progress edits separately
  before running it.
- [ ] Review the diff against the project's coding guideline / repo rules
  (project-specific conventions live there, e.g. naming prefixes, relational-write
  helpers). If a review pass already ran on this diff, don't re-dispatch — skim
  yourself for commits added after. If review was skipped, either check the guideline
  yourself or dispatch a review agent with the full `git diff` (not `--stat`) plus
  `git status` output (so untracked new tests/migrations get covered too).
  - Blocker findings must be fixed (by you, not by editing the test to assert the
    bug — see the Example instance below).
  - Should-fix/nit findings: fix opportunistically if cheap, else note in the final
    report.
- [ ] Verify the fix, don't just trust the review — run the specific tests flagged
  with an explicit path. `-k` alone with no path can skip loading `conftest.py`,
  producing a misleading `AttributeError: module 'odoo' has no attribute 'tools'` at
  pytest-odoo's `pytest_cmdline_main` hook — always pass a real file/dir path
  alongside `-k`.
  - The test database may not have the addon installed at all — check
    `select name, state from ir_module_module where name = '<addon>'` first. Pass the
    odoo config as a full path (a bare relative filename raises "config file doesn't
    exist") against the known-good dev DB.
  - The dev DB carries its own staleness — an `UndefinedTable`/`UndefinedColumn` on a
    model unrelated to your diff is likely pre-existing DB drift, not a regression;
    note it, move on. An error on a model your diff touched is real.
  - Never `git stash` mid-verification without immediately popping it — it also
    stashes your uncommitted fixes.
- [ ] Commit locally with a message per the project's commit style (e.g.
  `[TYPE] module_name: short desc`). Stop here unless the next bullet applies.
- [ ] Push + open the MR only if the user explicitly asked this session — never as
  an automatic follow-on. Order: fetch `upstream` → checkout/create the local
  working branch → `git add -A` + commit (skipped if clean) → rebase onto
  `upstream` → force-with-lease push to `origin` → open/reuse a cross-project MR
  `origin/<branch>` → `upstream/<branch>`, print the MR URL. On rebase conflict the
  script exits and tells you to resolve, then `git rebase --continue` and re-run
  (it skips the already-done commit and proceeds from rebase). Provider
  authentication needs an access token (`api` scope) exported — one-time setup;
  check `[ -n "$GITLAB_TOKEN" ]` first, don't `echo` the value.

  Report the MR URL to the user — don't just say "pushed."

## Example instance

- 2026-07-07 (prior suite): a supplement-line branch wrote a `product.template` id
  into a `Many2one('product.product')` field, and the accompanying test asserted that
  *wrong* value with a "KNOWN BUG" comment instead of catching it — generalized into
  the "fix blockers yourself, never by editing the test to assert the bug" review
  step above. Fix: drop the unnecessary `.product_tmpl_id` hop (`product.product`
  exposes `categ_id` via `_inherits`) and rewrite the test to assert correct
  behavior.
