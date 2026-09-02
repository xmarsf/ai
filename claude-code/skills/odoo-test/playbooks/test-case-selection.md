# Select which cases to test

Applies when: [write-odoo-tests](write-odoo-tests.md) is on the path (TDD / coverage
work needs a concrete case list) — **mandatory returning child; never optional**.
Also when a documented coverage gap needs case planning. Skip only for pure
declarative UI/schema (**module-update path**, no `write-odoo-tests`).

Parent playbook: [write-odoo-tests](write-odoo-tests.md) — returning sub-step; resume
the next parent step after this checklist. **If the parent runs, this child must
run** — open the full checklist; do not invent a case table without it.

## Usage
- used: 1
- last used: 2026-07-16

## Steps

- [ ] Name the **behavior under change** in one sentence (business outcome, not file
  list). If there is no business outcome, stop — module-update path, no cases.
- [ ] **Pull candidates from already-expanded feature playbooks** (parent order:
  [write-odoo-tests](write-odoo-tests.md) expands those first). Sample case lists
  in feature playbooks are **candidates**, not the finished table — still apply
  keep/drop rules below with cites.
- [ ] List **owned branches** from the plan / source **and** those candidates:
  happy path, each guard you add or change (`UserError`, constraint, state gate,
  access branch), **each entrypoint that can violate the invariant** (`create`,
  `write`, action, route — not write-only when create can bypass), explicit
  thresholds/edges, multi-company or multi-user only when the rule is scoped that way.
- [ ] Build a **case table** (keep in the plan / dispatch prompt):

  | case | trigger condition | entrypoint | assert (business result) | covered elsewhere? |
  | --- | --- | --- | --- | --- |
  | … | state/user/company/context | method / Form / route / tour | field/state/error | `module:Class.method` or — |

- [ ] **Drop rows** that are: pure ORM plumbing (field stores, standard M2O link);
  framework behavior; **declarative UI/schema** only; behavior fully owned and
  tested in a **dependency module** (cite `module:Class.method` in the table — do
  not re-assert). Adjacent branches marked deliberately-untested in a gap doc stay
  out unless this task owns them.
  **Do not drop as "framework":** create-path or write-path rows for an
  **owned business guard** you implement (e.g. state-gated `active=False` — ORM
  `active_test` is framework; **your** create/write gate is not). Dropping them
  forces a tdd follow-up later.
- [ ] **Default case catalog** (require only when applicable):
  - Happy path of *this* module's rule — always for new business behavior.
  - One negative per **owned** guard — each distinct failure mode you implement.
  - Boundary/edge — only if code has an explicit threshold or combinatorial branch.
  - Multi-company / as-user — only if the rule is company- or group-scoped.
  - Regression — always for a bug fix (must fail before the fix).
- [ ] Prefer **one behavior per test method**. "And" in the name → split. Minimal
  asserts: only fields/errors that prove the rule, not every field on the record.
- [ ] Prefer the **real entrypoint** that production hits (action, `create`/`write`,
  constraint, compute, Form assign, HTTP route). Do not replay a full lifecycle when
  one method call is the seam.
- [ ] When many independent dimensions (state × company × group × type) explode the
  matrix, reduce with pairwise/edge sampling — still only dimensions *this* change
  introduces; do not re-cover dependency-owned axes.
- [ ] Hand the finished case table to type selection and placement
  ([write-odoo-tests](write-odoo-tests.md) next steps, then
  [test-module-structure](test-module-structure.md) /
  [test-cross-module](test-cross-module.md) when multi-addon).

## Pitfalls

- Finishing this table **before** expanding the feature playbook that lists owned
  create/write cases — main cause of avoidable `followup_cycles` on archive-style
  work.
- Treating a sibling playbook's sample test list (or a hand-waved dispatch table)
  as a finished case table — still run this checklist; use those samples as
  candidates to keep/drop with cites.
- Marking create-with-`active=False` (or any dual-entrypoint guard) "covered by
  ORM / framework" when this change implements the guard.
- Coverage % is not a goal — meaningful assertions on owned outcomes are.
- "Covered indirectly" without a cited test is not coverage; name the owner or write
  a case.
- Do not re-test the ORM or standard Odoo flows already proven in core/dependency
  modules (Odoo tutorial: trust the ORM; business modules test business flows).
- Bug-fix cases must fail on current code for the bug reason, not for setup typos.
- Do not invent negative cases for guards this change does not implement.

## Example instance

- Gap doc listed five RFQ steps; only one was truly uncovered. Case table kept one
  happy-path action chain + one guard; three rows cited existing
  `<module>:TestRfqState.test_*` cases and were dropped — no duplicate suite.

## Relevant knowledge-base

- note: Unit Test Odoo — entrypoints, assert patterns
- Odoo tutorial "Safeguard your code with unit tests" — don't re-test elsewhere; trust ORM
