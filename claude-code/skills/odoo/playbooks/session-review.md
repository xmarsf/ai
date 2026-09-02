# Review one orchestrated task session

Applies when: the user asks to review, audit, or run a retrospective on one completed
`odoo-orchestrate` task session, focusing on execution adherence, verification gaps,
and reusable workflow lessons rather than sweeping the whole playbook system.

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 0
- last used: n/a

## Steps

- [ ] **Freeze the session evidence.** Collect the original request, applicable
   repository instructions, working plan, specialist prompts/returns, tool results,
   final diff/status, verification results, and final user report. Prefer direct
   evidence over the session's own summary.
- [ ] **Audit [SKILL.md](../SKILL.md)'s opening protocol and playbook matching.**
   Per step: expected vs actual +
   evidence + gap. Include auth boundaries and dirty-worktree preservation. Check
   glossary controls: **pipeline_depth**, **lazy expansion** (top-level only at step
   0), **test surface** → tdd tier, **test ownership** / infrastructure carve-out,
   **usage_counters_bumped**, **zero-token** (`export_plan` when N× shape, no
   re-derivation of matched playbooks, deterministic tools over reasoning loops,
   `exports_this_run` at close).
- [ ] **Classify each gap:** execution miss | guidance gap | external blocker |
   implementation defect | **zero-token miss** (re-inferred a captured shape, hand-authored
   N near-copies without export, left a recurring lesson only in chat).
- [ ] **Implementation defects** → finish via original workflow (not the retrospective).
- [ ] **Before durable lessons**, search all stores (playbooks, RULES, vault,
   glossaries, existing scripts/helpers). No new guidance for an execution miss already covered.
- [ ] **Route genuine guidance gaps through [reference/updating.md](../reference/updating.md).** Update the
   narrowest existing owner first (incl. **export artifact** when the lesson is a
   deterministic transform). Create a new category only when its admission test
   passes. Keep concrete session names in `## Example instance`, not Steps/Pitfalls.
- [ ] **Repair close-out bookkeeping.** Update usage counters only for playbooks
   actually followed; do not create dated audit/history prose merely to show that the
   session was reviewed.
- [ ] **Report the retrospective.** Rank concrete misses/defects first, then summarize
   durable workflow changes, unchanged guidance and why, verification blockers, and
   whether this was a single-session review or a full playbook-system sweep.

## Pitfalls

- Do not rely only on the final answer when tool output, agent returns, or the actual
  diff can confirm what happened.
- Do not rewrite a playbook to compensate for failing to follow guidance that was
  already correct; classify it as an execution miss.
- Do not label a test green when its process never started, or label an approval/
  infrastructure timeout as a product-code failure.
- Do not let retrospective cleanup broaden authority into committing, pushing,
  posting, deleting, or changing unrelated dirty-worktree content.

## Example instance

- 2026-07-13, customer enterprise type and bank CITAD fields: the session review
  separated an early repository-instruction miss from a real one2many input-surface
  playbook gap, and distinguished two approval-blocked test starts from test failures.

## Relevant knowledge-base

No direct topic — this is process review. Route any Odoo behavior fact uncovered by
the audit through the `knowledge-base` lookup/write-back flow.
