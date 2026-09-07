# form-view-dialog-replacement

Applies when: replacing an `ir.actions.act_window target="new"` flow with a custom
Owl `FormViewDialog`, especially when a nested action popup would close or replace a
parent action dialog.

Parent playbook: [inherit-view](inherit-view.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] **Confirm the nested-action failure mode first.** Reproduce or trace whether the
   existing button returns an `ir.actions.act_window` with `target="new"` from inside
   another action dialog, and cite the relevant Python method/view button.
- [ ] **Use the dialog service, not another action.** Open `FormViewDialog` through
   `dialogService.add(...)` (note: Odoo Actions, below).
- [ ] **Resolve the form view through a public client path.** Do not call private
   (`_`-prefixed) methods from JS RPC. Use a public ORM call such as `searchRead` on
   `ir.model.data`, or add a small public model method when access or reuse requires
   it.
- [ ] **Keep the interception narrow.** Patch or extend the smallest existing frontend
   component that has both button metadata and the clicked record, and guard by model,
   button name/type, and a required `resId`.
- [ ] **Preserve pre-open save behavior.** If the original object button was in an
   editable form/list, save the clicked dirty record before opening the dialog; abort
   if the save fails validation.
- [ ] **Mark the custom dialog context.** Pass a context flag into `FormViewDialog` so
   any special footer handling can distinguish this dialog from ordinary forms of the
   same model.
- [ ] **Prevent footer `act_window_close` from escaping to the parent action dialog.**
   If the reused form view has footer object buttons returning
   `ir.actions.act_window_close`, intercept those buttons in the custom dialog context
   and close via `env.dialogData.close()` after saving/discarding.
- [ ] **Refresh the parent record after close/save.** Reload the originating record or
   parent model after a successful dialog save so inline summary fields/tags reflect
   the saved child data.
- [ ] **Check asset registration and syntax.** Confirm the new JS file is included in
   backend assets, run a cheap JS syntax check when available, and run focused Odoo
   tests only through the project's Odoo-aware harness.

## Pitfalls

- A form view footer button like `<button type="object" name="save_and_close">` can
  still return `act_window_close`; inside a custom `FormViewDialog`, that action may
  close the parent action dialog instead of the custom dialog unless intercepted.
- Remote ORM calls cannot invoke methods whose names start with `_`; use public ORM
  methods from JS, or expose a public server helper intentionally.
- `FormViewDialog` may save and close correctly while the parent inline row remains
  stale unless the originating record is reloaded.

## Relevant knowledge-base

- `note: Odoo Actions` — `target="new"` action dialogs are not nested as a stack.
- `source: odoo/addons/web/static/src/core/dialog/dialog_service.js:dialogService.start` — the
  dialog service pushes dialogs onto a stack.
- `source: odoo/addons/web/static/src/views/view_dialogs/form_view_dialog.js:FormViewDialog` —
  `FormViewDialog` props include `resModel`, `resId`, `viewId`, callbacks, and size.
- `source: odoo/service/model.py:get_public_method` — private methods cannot be called remotely.
