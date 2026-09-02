# Mail activity deduping across recomputes

Applies when: a stored compute repeatedly schedules mail.activity warnings, and you need to dedupe across multiple recompute cycles.

Called by: [implement-model](implement-model.md), [implement-notification](implement-notification.md)

## Usage
- used: 1
- last used: 2026-07-10

## Steps
- [ ] Match existing activities on a stable key (`activity_type_id` + `summary`), not exact `note` content
- [ ] Do NOT match on `note`: `mail.activity.note` is an `Html` field and gets re-wrapped/sanitized on every write, so a freshly built plain-text string never equality-matches the persisted value
- [ ] Overwrite the existing activity's `note` in place instead of trying to recreate it
- [ ] Unlink the activity once the triggering condition clears, so a resolved warning doesn't stay open forever

## Pitfalls
- Matching on exact `note` content: the first scheduled activity has `note` as plain text; when you check for an existing activity and try to match that plain text, the sanitized/re-wrapped DB value never equals it, causing a duplicate every recompute cycle
- Not unlinking when the condition clears: warning stays in activity checklists forever, even after the issue is resolved

## Example instance
- Check: `activities = self.env['mail.activity'].search([('res_id', '=', self.id), ('res_model', '=', self._name), ('activity_type_id', '=', activity_type.id), ('summary', '=', 'Warning')])`
- Update: `if activities: activities[0].note = new_note_html` 
- Delete: `if not condition_still_holds: activities.unlink()`

## Relevant knowledge-base

- No dedicated note yet for `mail.activity.note`'s Html-sanitization/re-wrap-on-write
  behavior — verify against `mail.activity`'s field definition before relying on this.
