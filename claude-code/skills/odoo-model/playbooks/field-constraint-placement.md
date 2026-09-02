# Deciding where to implement domain / readonly / required on a field

Applies whenever a task asks for a constraint on a field — "this field should be
required when X", "read-only after confirm", "only show records matching Y" — and you
need to decide: Python field kwarg, XML view attribute, or both. This is a process
heuristic (how to *think*), not a place to relitigate the underlying facts — those
live in `knowledge-base`'s `XML View` note (see pointer below). Verify the facts
still hold before trusting this from memory; code moves on.

Called by: [add-sibling-domain-many2one-field](add-sibling-domain-many2one-field.md), [implement-field](implement-field.md), [inherit-view](../../odoo-view/playbooks/inherit-view.md)

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Decision heuristic

The asymmetry driving this choice — `readonly`/`required` fall back to the Python
default, `domain` does not — is documented in the `XML View` note below; verify it
there before trusting this from memory, don't relitigate it here.

- [ ] **`readonly`/`required` that should hold everywhere** → set in Python on the
  field. Repeat in a specific view's XML only to loosen/tighten it there (wizard
  needs it editable, state-dependent expression Python can't express).
- [ ] **`domain` meant to restrict UI selection** → declare it in the XML of every
  view where the restriction should apply; verify by checking whether the `<field>`
  node in the view you're touching already repeats it. Don't rely on the Python
  `domain=` kwarg alone.
- [ ] **Same domain needed across many views/fields** → define it once as a named
  `<filter name="..." domain="...">` on the target model's search view, then set
  `context="{'search_default_<filter_name>': 1, 'some_key': <sibling_field>}"` on
  each `<field>` that should apply it. Trade-off: this only reaches the "Search
  More" popup, not the inline autocomplete dropdown — flag that to the requester if
  the dropdown also needs narrowing, since that still requires a literal `domain=`
  attribute on the field.
- [ ] **When in doubt about current behavior** → grep the view file for whether the
  `<field>` node repeats the domain; don't assume from general Odoo knowledge. Check
  `knowledge-base`'s `XML View` note (section "domain: KHÔNG có Python-fallback như
  readonly/required") for source-cited mechanics.

## Relevant knowledge-base pointers

- `XML View` note, sections "readonly: XML đè Python" and "domain: KHÔNG có
  Python-fallback như readonly/required" — source-cited (`field.js`,
  `many2one_field.js`, `fields_relational.py`) mechanics for both asymmetries.
- `Odoo domain` note — `parent.` prefix scope, and store/searchable requirements for
  server-side vs client-side domain leaves.

## Example instance

- 2026-07-05, [add-sibling-domain-many2one-field.md](add-sibling-domain-many2one-field.md) run: `connecting_flight_id` was
  first implemented with the domain only on the Python field; the correct fix was a
  view-level search filter auto-applied via context (point 3 above) — this asymmetry
  surfaced from verifying *why* that request was correct, not just doing it.
