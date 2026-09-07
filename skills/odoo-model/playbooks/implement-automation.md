# Implement automation (cron / server action / automated rule)

Applies when: a task adds or changes a scheduled job (`ir.cron`), a menu/button-
triggered `ir.actions.server`, or a create/write/time-triggered `base.automation` rule.

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 0 (tracking started 2026-07-16)
- last used: n/a

## Steps

- [ ] Pick the trigger shape first: time-based recurring → `ir.cron`; user-triggered
  from a menu/button/action → `ir.actions.server`; fires off another record's
  create/write/time condition → `base.automation`.
- [ ] Define `ir.cron`/`base.automation` records via XML data, not by hand-creating them
  through the UI only — they must ship with the module.
- [ ] The method a cron/automation calls must be batch-safe: search once, process the
  whole recordset, no per-record loop with its own commit.
- [ ] Wrap per-record processing in the cron/automation body so one record's exception
  is caught and logged, not left to abort the whole run — an uncaught exception blocks
  every subsequent scheduled run until the cron is manually re-enabled.
- [ ] `base.automation`: scope the trigger (`on_create`/`on_write`/`on_time`) and its
  domain as tightly as the actual condition — an overly broad domain fires on unrelated
  writes and can loop back into the same model's own recompute. Automation writes back
  onto the triggering model/field → run playbook:
  [compute-onchange-safety](compute-onchange-safety.md).
- [ ] Cron/automation runs as `ir.cron.user_id` (often an internal/system user), not the
  developer's own session — verify the method's field/model access assumptions hold
  under that user before trusting a green manual test.
- [ ] Any user-facing name/label (cron name, server action name) → run playbook:
  the **odoo-wlc** skill (translation round-trip).
- [ ] Verify by triggering the job directly (call the bound method, or
  `env['ir.cron'].sudo().browse(id)._trigger()`) rather than waiting for the real
  interval to elapse.

## Pitfalls

- Per-record commits inside a cron loop break batch semantics and don't scale; process
  the full recordset in one pass instead.
- An unhandled exception on one record silently fails the whole scheduled run and can
  leave the cron marked as failed/disabled with no per-record diagnostic.
- A `base.automation` domain broad enough to match its own side-effect writes creates a
  recompute/notification loop.

## Example instance

- (seed entry — fill in with the first run that adds a cron/server action/automation
  through this playbook: trigger shape chosen, batch method, and the running-user
  verification.)

## Relevant knowledge-base

- No dedicated vault note yet for `ir.cron`/`base.automation` execution-user and retry
  semantics — verify against source before relying on this playbook alone, and write
  back a note after the first orchestrated run.
