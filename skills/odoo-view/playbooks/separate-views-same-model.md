# Separate views on the same model

Applies when: one model needs two (or more) distinct UIs — different form/list layouts
with independent menu entries/navigation — and each entry point, including page reload
and Many2one navigation, must land on the right variant.
Seeded from knowledge-base (note: Separate Views Same Model) — not yet validated by an
orchestrated run.

Called by: [inherit-view](inherit-view.md), [implement-view](implement-view.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Create the alternate form view as a `mode="primary"` inherit of the base form —
  it diverges freely without polluting the base (note: Separate Views Same Model §1).
- [ ] Create the alternate list view as a standalone view record.
- [ ] Create a dedicated `ir.actions.act_window` for the alternate UI with its own
  domain/context.
- [ ] Bind the views to the action via `ir.actions.act_window.view` records, one per
  view mode — not the `views` field eval trick (compat:act-window-views-binding:
  action `views` is a compute-only field, so eval binding does not persist on
  17/18/19; `ir.actions.act_window.view` records are the stable form); note:
  Separate Views Same Model §3).
- [ ] Where Python code returns or adjusts the action, fetch it via `_for_xml_id()`
  (note: Separate Views Same Model §4).
- [ ] Route Many2one navigation from other screens into the alternate form via
  `context="{'form_view_ref': '<xml id>'}"` on the referencing field.
- [ ] Verify each entry point separately: menu click, Many2one breadcrumb, and a full
  page reload on a record URL — reload resolves through the action, not the view you
  navigated from.

## Pitfalls

- Setting the action's `views` field via `eval` bindings looks like it works until a
  reload or breadcrumb navigation re-resolves the action — use
  `ir.actions.act_window.view` records instead.

## Relevant knowledge-base

- note: Separate Views Same Model — primary-mode inherit semantics, act_window.view
  binding, `_for_xml_id`, `form_view_ref` routing, reload resolution order.
