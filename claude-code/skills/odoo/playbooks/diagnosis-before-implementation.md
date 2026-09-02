# diagnosis-before-implementation

Applies when: the task shape is "why does this specific record/screen show
unexpected behavior/data" — before any code change, gather evidence and map the
symptom to source. Distinct from implementing a known feature/fix, where the
behavior change itself is already the goal.

Entry point: [SKILL.md](../SKILL.md)
Called by: [live-debug](../../odoo-debug/playbooks/live-debug.md), [local-record-debug](../../odoo-debug/playbooks/local-record-debug.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] **Classify the task-evaluation result as diagnosis first**: effort is usually
   `S`/`M`, and the test strategy is one-time reproduction before persistent tests —
   only add persistent tests once a repo-side bug is confirmed, not while still
   diagnosing.
- [ ] **Gather evidence before touching code** — DB query, RPC read (see
   run playbook: [xmlrpc-live-query](../../odoo-debug/playbooks/xmlrpc-live-query.md) when the target is a live/remote instance), or
   local reproduction. Don't reason from the bug report's prose description alone.
- [ ] Posting a bill/journal entry fails with a date-vs-sequence `ValidationError`?
   → run playbook: [account-sequence-date-mismatch-triage](../../odoo-debug/playbooks/account-sequence-date-mismatch-triage.md)
   (data triage, not a code change).
- [ ] **Map evidence back to source**: search the repo for the model/view/action/
   controller/traceback function implicated, and cite file:function_name. Prefer source
   citations over inference from the UI. If the evidence points at Odoo framework
   behavior, use `knowledge-base` and cite the note or source line — keep Odoo
   domain mechanics out of this playbook.
- [ ] **Separate environment/data issues from code defects** before planning a fix —
   a live-only or record-only data/config anomaly gets a reproduction note plus a
   suggested data fix, not a repo patch. Verify current code logic by reproducing it
   directly (test, shell, or an isolated call to the exact method), not by comparing
   timestamps or inferring from field definitions in isolation — the object that
   actually produced a given record may have gone through a different code path
   than the field's own compute would suggest.
- [ ] **Report the traced chain and a verified verdict** (data-only vs. code bug)
   with file:function_name citations, not a probability estimate.
- [ ] **Promote to the normal orchestrate flow only after the defect is scoped in
   source**: re-run [task-evaluation](task-evaluation.md) broad-shape matching on the
   now-scoped fix — a code-level bug fix or logic extension on an existing model
   routes to [implement-model](../../odoo-model/playbooks/implement-model.md) (existing-model branch, see
   [inherit-model](../../odoo-model/playbooks/inherit-model.md)); a declarative-only defect (view/security/report)
   routes to its own broad shape. Add persistent tests if the behavior can regress,
   implement, and verify against the original reproduction steps.

## Relevant knowledge-base

Process only — route any Odoo domain-fact claim surfaced during diagnosis through
`knowledge-base`'s own index/write-back flow instead of duplicating it here.
