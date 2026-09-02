# one2many-list-display-columns

Applies when: a task changes visible columns, labels, ordering, or display-only
values inside an Odoo one2many/list subview.

Parent playbook: [inherit-view](inherit-view.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 1
- last used: 2026-07-13

## Steps

- [ ] Locate the parent form view and the embedded `<field>/<list>` node, then identify the
   backing line model, the method that populates line values, and the actual create/edit
   surface (inline list, popup form, or both).
- [ ] Ground view behavior first. Useful pointers:
   - `note: XML View`
   - `source: addons/web/static/src/views/fields/field.js:Field.parseFieldNode`
   - `source: addons/web/static/src/views/fields/formatters.js:formatPercentage`
- [ ] Add focused tests before implementation:
   - one test parses `get_view()` and asserts list field ordering plus hidden columns;
   - when create/edit uses a popup form, one test asserts the field is present and
     correctly ordered in that compiled form too;
   - one data-flow test asserts newly displayed values are prepared from the correct
     source field.
- [ ] Implement model/view changes narrowly:
   - add an input field to every create/edit surface users reach, not only the list
     column that displays the value;
   - keep snapshot document fields as copied scalar fields, not live related fields,
     unless the surrounding model is already consistently live;
   - raw 0-100 value → do not use the **percentage widget**;
   - avoid explicit `string=` in XML when the field label plus i18n field_description is
     sufficient; any translation additions go through the **odoo-wlc** skill.
- [ ] Verify with full Odoo tests via `odoo runtime-test` against the DB from
   `config/project.json`. If no DB is configured/reachable there, at least run
   Python compile, XML parse, scoped file-level assertions, and `git diff --check`.

## Pitfalls

- A column added only to a non-inline-editable one2many list may display imported or
  existing values while leaving users no place to enter them; trace the row create/edit
  path and update its popup form when applicable.
- Stored related fields can make old documents drift when the source record's data
  changes later. Copy the value during document creation if the rest of the document
  line is a snapshot.
- XML `string=` overrides field labels in the compiled view, so field_description
  translations alone may not translate those column headers (note: XML View).
- Reordering a column via `<xpath position="move">` nested inside an outer
  `<xpath position="before|after|inside|replace">` is a valid, standard Odoo
  inheritance pattern, not a workaround to second-guess — see
  `source: odoo/tools/template_inheritance.py:add_stripped_items_before+apply_inheritance_specs.extract` and
  `knowledge-base`'s `XML View` note.
