# Triage a journal-entry sequence/date mismatch

Applies when: posting a bill/journal entry fails with a `ValidationError` about the
document date conflicting with existing sequence numbers — a data triage operation on
a live/dev database, not a code change.
Seeded from knowledge-base (note: Account Sequence) — not yet validated by an
orchestrated run.

Entry point: [the odoo skill](../../odoo/SKILL.md)
Called by: [diagnosis-before-implementation](../../odoo/playbooks/diagnosis-before-implementation.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Determine scope first: one draft entry, or a batch that must keep numbering
  continuity — the fix differs (note: Account Sequence).
- [ ] Single draft entry: clear its `name` and let Odoo re-assign the next valid
  number on post.
- [ ] Batch needing continuity: use `account.resequence.wizard` (dev mode); expect it
  to be blocked on hash-locked journals (note: Account Sequence).
- [ ] Never bypass or patch around `_constrains_date_sequence()` — the constraint is
  the integrity guarantee, not the bug.
- [ ] If the root cause is unwanted period-based numbering, change the journal's
  sequence format instead of fighting individual entries (note: Account Sequence).

## Pitfalls

- Hand-editing `name` to a "free" number satisfies the immediate error but corrupts
  the sequence chain the constraint protects — always let Odoo assign or resequence.

## Relevant knowledge-base

- note: Account Sequence — how journal sequence numbers derive from date + format,
  `_constrains_date_sequence()` semantics, resequence wizard limits on locked
  journals.
