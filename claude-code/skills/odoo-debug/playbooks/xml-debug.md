# Debug Odoo XML loading and validation

Applies when: an Odoo XML/data/security file raises `ParseError`,
`ValidationError`, or `Invalid view`, or an XML change installs/upgrades without
taking effect.

Entry point: [the odoo skill](../../odoo/SKILL.md)
Called by: [inherit-view](../../odoo-view/playbooks/inherit-view.md), [implement-view](../../odoo-view/playbooks/implement-view.md)

## Usage
- used: 0
- last used: n/a

## Steps

- [ ] Read the complete traceback and identify the inner exception immediately
  before the wrapping `ParseError`; record the reported file and line.
- [ ] Classify the failure before editing: XML/RNG structure, view validation,
  data/constraint execution, security CSV, or a loaded-but-unchanged record.
- [ ] For XML/RNG structure, parse the file locally and validate the affected view
  architecture against the matching schema when available; inspect unsupported
  tags/attributes and invalid `decoration-*` names.
- [ ] For view validation, verify every referenced field exists with the installed
  dependencies, each widget fits the field/view type, and legacy `attrs`/`states`
  syntax has been converted to direct modifiers (compat:view-attrs-states —
  removed in every supported major; use attribute-level `invisible`/`readonly`/
  `required` expressions).
- [ ] For inherited views, verify the anchor against the active parent architecture,
  apply rule: [xml] inherited-view replacement, and inspect the effective rendered
  architecture for a silent no-op.
- [ ] For `ir.model.access.csv`, run playbook:
  [implement-security-rule](../../odoo-model/playbooks/implement-security-rule.md) and validate the header,
  external IDs, and row shape before returning here.
- [ ] For data or constraint failures, trace the referenced-record load order and
  any custom `create()`/`write()` validation reached during import; narrow the guard
  to the fields and transition actually being changed.
- [ ] If an update succeeds but the value does not change, inspect `noupdate`
  ownership and the current database record before changing XML again.
- [ ] Run the repository's real module install/update command with focused convert/
  view logging, then verify the effective database/view result rather than stopping
  at a clean XML parse.

## Pitfalls

- The line reported by `ParseError` can point at the surrounding record rather than
  the invalid descendant; use the inner exception and schema/view validation output.
- A valid XML document can still fail Odoo view validation or execute model business
  constraints during data import.
- A successful upgrade does not prove the intended record changed when `noupdate`,
  record ownership, or an unmatched inherited-view anchor is involved.
- Do not hard-code one repository's Docker/database command into the diagnosis;
  discover and use the active checkout's runner.

## Relevant knowledge-base

- `XML View` note (vault: `6- Main doc/XML View.md`)
- `Views` note (vault: `6- Main doc/Views.md`)
- `Odoo View Patterns` note (vault: `6- Main doc/Odoo View Patterns.md`)
- `Odoo Security` note (vault: `6- Main doc/Odoo Security.md`)
