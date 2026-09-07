# live-debug

Applies when: the user asks to debug a live/dev Odoo URL directly, especially with
credentials and db/host details provided via a local `.env` file. Diagnosis-first:
don't treat the live server as the place to make code changes — reproduce, gather
evidence, then map the problem back to repo code, data, config, or deployment state.

Entry point: [the odoo skill](../../odoo/SKILL.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Run playbook [diagnosis-before-implementation](../../odoo/playbooks/diagnosis-before-implementation.md)
  — impact = the screen being debugged; split decision = proceed unless the symptom
  expands.
- [ ] Load credentials without exposing them: read only the relevant `.env` path,
  redact terminal output, never paste account/password/token/cookie/db/host details
  anywhere (playbook, report, agent prompt, issue) — refer to path/key names instead.
- [ ] Preserve the exact target context: full URL including `action-<id>`, record id,
  query params (`debug=1`), db — don't reduce to the menu name.
- [ ] Use RPC first, not a browser session — run playbook
  [xmlrpc-live-query](xmlrpc-live-query.md) for connection/credential rules; target
  `ir.actions.*` reads and safe read-only methods. Escalate on sandboxed-network
  blocks rather than switching approach.
- [ ] Use browser evidence only when RPC can't observe the bug (client rendering,
  assets, tour, JS-console); also capture server traceback text and exact
  user-visible messages.
- [ ] Map live evidence back to source: model, view XML ID, action domain/context,
  controller route, JS asset, or traceback function names — prefer source citations
  over UI guesses. Cite a knowledge-base note/source line for framework behavior
  claims; keep domain mechanics out of this playbook. Confirm technical field/comodel
  via source or RPC `fields_get` before searching by a translated label (Example
  instance).
- [ ] Separate environment/data issues from code defects: check record, company,
  groups, language, cache/assets, deployment revision before planning a code change —
  a live-only data/config issue gets a repro note + admin/data fix, not a patch. For
  product FK/delete errors, compare template/product/`product_variant_id` via RPC
  (note: Common ORM Method).
- [ ] Promote to normal orchestrate flow once the defect is scoped: matching
  feature/bug-fix playbook, regression tests if applicable, implement locally, verify
  against the original repro. Verify the local db has the addon schema
  (`to_regclass` check) before trusting a same-named test db.
- [ ] Report without secrets: URL shape, sanitized credential path, repro steps,
  evidence, suspected sources, tests run, blockers — no raw credentials/cookies/
  headers/payloads.

## Pitfalls

- Never hard-code live credentials into scripts, profiles, tests, or playbooks —
  `.env` is the only source of secret material, keep it local.
- `debug=1` doesn't mean the user is already in developer mode after login — preserve
  it as context and query the same action/record via RPC post-auth.
- A live action URL can depend on db data as much as code — if local search can't
  find the id, inspect source and live metadata separately rather than inventing a
  mapping.
- Avoid mutating live/dev data unless explicitly asked; prefer read-only repro and
  local fixes.
- If RPC can't reproduce an on-screen complaint, don't jump to code changes — first
  decide if it's client state, assets/cache, company/group/language context, or a
  genuinely UI-only bug. A browser fallback that only succeeds after cache
  clearing/asset rebuild is deployment/cache evidence, not a code-patch signal.
- Don't trust id equality between related models as a fixture assumption — seed data
  often has matching template/variant ids, hiding a template-id-in-variant-field bug
  until a live record's ids diverge; use a mismatch case for regression tests.

## Example instance

- An error dialog showed the translated label "Món ăn" (field `string=`); the
  technical field was `product_id`. Searching live records by the displayed text
  instead of the technical name would have missed the record.

## Relevant knowledge-base

- Use `XML View`, `Views`, `Odoo Fields`, or `Common ORM Method` notes (vault: `6-
  Main doc/`), or direct source citations, only when live evidence becomes a
  load-bearing Odoo behavior claim. `Common ORM Method` covers `Many2one` write
  values and x2many command shapes. This playbook stores the debug sequence, not
  Odoo domain facts.
