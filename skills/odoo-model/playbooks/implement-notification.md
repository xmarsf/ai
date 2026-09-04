# Implement a notification (mail template / activity / follower message)

Applies when: a task adds or changes an outbound `mail.template` email, a follower
notification (`message_post`), or a user-facing reminder (`activity_schedule`) as the
feature itself — not the incidental dedupe-across-recomputes pitfall already covered by
[mail-activity-deduping](mail-activity-deduping.md).

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 0 (tracking started 2026-07-16)
- last used: n/a

## Steps

- [ ] Pick the channel to match the intent: templated outbound email →
  `mail.template` triggered via `message_post_with_template`/a compose wizard;
  in-app/portal notification → `message_post` with an explicit `subtype_xmlid`;
  actionable reminder assigned to a user → `activity_schedule`.
- [ ] `mail.template`: bind it to the right model, use `object.<field>` placeholders
  (not raw Python string interpolation into the body), and confirm the subject/body
  render correctly under a non-default user language, not just the developer's own.
- [ ] Choose the message subtype deliberately: `mail.mt_note` (or no subtype) for
  internal-only notes vs. a customer-visible subtype for portal-facing updates — the
  wrong choice either hides an update from the followers who need it or exposes an
  internal note to a portal/customer follower.
- [ ] Schedules a repeating activity from a stored compute → run playbook:
  [mail-activity-deduping](mail-activity-deduping.md) to avoid duplicate/orphaned
  activities across recompute cycles.
- [ ] Any subject/body/label string → run playbook: the **odoo-wlc** skill (translation round-trip).
- [ ] Verify by actually triggering the send/post path (not just asserting the
  rendered template string) and inspecting the resulting `mail.message`'s subtype and
  recipient partners.

## Pitfalls

- Wrong subtype: internal note leaks to portal/customer followers, or a genuinely
  customer-facing update stays invisible to them.
- String-formatting record data directly into an HTML body bypasses both the
  template's auto-escaping and its translation extraction.

## Example instance

- (seed entry — fill in with the first run that adds a notification through this
  playbook: channel chosen, subtype, and how the send path was verified.)

## Relevant knowledge-base

- No dedicated vault note yet for `mail.template`/subtype visibility rules — verify
  against `mail.thread`/`mail.template` source before relying on this playbook alone,
  and write back a note after the first orchestrated run.
