# Guard a state-transition action button against double triggering

Applies when: adding or reviewing a `type="object"` button whose method transitions a
record's state, whether or not it also triggers a downstream chain (stock moves,
journal entries, created linked records) — double clicks or direct RPC calls must not
re-run the transition (or the chain) twice.
Seeded from knowledge-base (note: Action Button Guard) — not yet validated by an
orchestrated run.

Parent playbook: [implement-model](../../odoo-model/playbooks/implement-model.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Map the trigger chain first: every side effect the method causes, directly or
  via triggered logic — the guard must protect all of it.
- [ ] Add the server-side state guard as the first line of the method: raise
  `UserError` if the record is already in/past the target state (note: Action Button
  Guard, Pattern 1).
- [ ] Add the UI layer on the button: `invisible=` on the expected state plus
  `disable_on_click="1"` (note: Action Button Guard, Patterns 2 & 4).
- [ ] Check every branch of the method, not just the main path — early returns and
  conditional sub-flows must sit behind the same guard.
- [ ] For high-contention records, consider row locking (`SELECT ... FOR UPDATE
  NOWAIT`) per the note's concurrency pattern before the state check.
- [ ] Cross-check the idiom against a core example of the same shape (the note cites
  base validate/post buttons) before inventing a variant.

## Pitfalls

- A UI-only guard (invisible/disabled button) passes manual testing every time and
  still double-fires under a fast double click or a scripted RPC call — the
  server-side state check is the load-bearing part.

## Relevant knowledge-base

- note: Action Button Guard — guard patterns (server state check, button invisibility,
  disable_on_click, row locking), core examples of each.
