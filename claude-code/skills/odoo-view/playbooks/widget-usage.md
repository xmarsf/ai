# Widget field type matching

Applies when: selecting or customizing widgets for specific field types in views.

Called by: [inherit-view](inherit-view.md), [implement-view](implement-view.md)

## Usage
- used: 1
- last used: 2026-07-10

## Steps
- [ ] Use the **percentage widget** only when the stored value is a fraction.
- [ ] When a falsy Char must remain visible in readonly/list rendering, inspect the
  candidate widget's `formattedValue` and readonly template; verify the fallback in
  the rendered cell, not only the edit-mode input placeholder.
- [ ] For Accounting's placeholder widgets, prefer
  `char_with_placeholder_field`; use `char_with_placeholder_field_to_check` only
  when the target record supplies `checked` and `state` and the "To review" badge is
  intended. Verify the owning module is a dependency so its field widget is loaded.

## Pitfalls
- Treating `placeholder="/"` as sufficient for readonly display: the standard Char
  template applies it to the editable input, while its readonly span renders the
  formatted field value.
- Treating `char_with_placeholder_field_to_check` as a generic fallback widget: its
  visible placeholder comes from the parent widget; the child also reads Accounting
  review fields and may render a badge.

## Example instance
- `account.move.name` in an invoice list uses
  `widget="char_with_placeholder_field_to_check" placeholder="/"`: a falsy name is
  shown as muted `/`, and posted unchecked moves can show the review badge.

## Relevant knowledge-base

- note: Odoo Glossary — percentage widget.
- source: `addons/web/static/src/views/fields/char/char_field.xml:web.CharField` — standard
  readonly span versus editable input placeholder.
- source: `addons/account/static/src/components/char_with_placeholder_field/char_with_placeholder_field.js:CharWithPlaceholderField`
  and `char_with_placeholder_field.xml:account.CharWithPlaceholderField` — readonly fallback and muted styling.
- source: `addons/account/static/src/components/char_with_placeholder_field_to_check/char_with_placeholder_field_to_check_to_check.js:CharWithPlaceholderFieldToCheck`
  and `char_with_placeholder_field.xml:account.CharWithPlaceholderField` — inherited fallback plus review badge.
