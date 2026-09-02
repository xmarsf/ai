# Form dialog patterns

Applies when: opening dialogs (target="new" act_windows) from within forms or other dialogs.

Parent playbook: [inherit-view](inherit-view.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 1
- last used: 2026-07-10

## Steps
- [ ] Never open a second `target="new"` act_window dialog from inside an open dialog — Odoo tracks only one active dialog; the new one replaces the old, leaving the user with no way back
- [ ] If you need a multi-step dialog flow: close the first dialog, return its result, then open the second from the parent form

## Pitfalls
- Stacked dialogs: opening dialog B from dialog A leaves dialog A inaccessible; user must close B to return, but form state from A is lost

## Example instance
- Bad: Button in a wizard dialog opens another wizard dialog with `target="new"`
- Good: First wizard completes, returns result to form. Form then opens second wizard via a new action.

## Relevant knowledge-base

- No dedicated note yet for the single-active-dialog-stack mechanic — verify against
  `dialog_service.js` before relying on this if the behavior seems to have changed.
