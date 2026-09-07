# local-record-debug

Applies when: the user reports unexpected data on a specific local dev-DB record
(e.g. "check contract id 674, field X looks wrong") and asks why, using the local
`odoo.conf` database directly — not a remote/live server reached via `.env` + RPC
(use `live-debug` for that case instead).

Entry point: [the odoo skill](../../odoo/SKILL.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] run playbook: [diagnosis-before-implementation](../../odoo/playbooks/diagnosis-before-implementation.md) — gather evidence and map to
  source before touching code.
- [ ] **Read the record and its relevant relations via `psql`** against the local
  `odoo.conf` database (see `reference_odoo_knowledge`/project memory for connection
  details) to get ground-truth field values — don't guess from the UI description
  alone.
- [ ] **Trace the write path in source**: find every place that creates or writes the
  suspect field (`grep` for the field name across the addon), and follow the actual
  call chain that produced this record (e.g. which wizard/action/`create()` populated
  it), not just the field's own model definition.
- [ ] **Verify current code logic directly, not via commit timestamps.** Do not try to
  establish whether a data anomaly predates or postdates a code fix by comparing
  `git log` commit timestamps against record `create_date`/`write_date`. Timestamps
  don't prove execution order (server clock vs commit clock, uncommitted local
  edits, migrations, manual data fixes), so this reasoning is speculative and easy to
  get backwards. Instead, reproduce the current logic directly: write or run a test
  (or an isolated call to the exact method in question, e.g. via `odoo shell` /
  pytest-odoo) against the current code to see what it actually produces for
  equivalent input today. If the current code produces the correct result, the
  anomaly is data-only (safe to note as a one-off/backfill item); if it doesn't, it's
  a live code bug — fix it and add a regression test.
- [ ] **Report the traced chain and verified verdict** (data-only vs code bug) with
  file:function_name citations, not a probability estimate.

## Pitfalls

- Field/model definitions can look correct in isolation while the actual object that
  produced a given record went through a different code path entirely (e.g. a
  conversion method that copies a value from a *different* source than the field's
  own compute would use). Always confirm which creation path actually ran for the
  record in question before reasoning about why a value is wrong.
- Multiple models can have similarly-named fields (e.g. `service_class_id` on a menu
  line vs a standard-line vs a menu itself) that are populated independently. Don't
  assume they're kept in sync unless the source shows an explicit copy/write between
  them.
