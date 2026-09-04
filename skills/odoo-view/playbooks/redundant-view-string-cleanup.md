# Redundant view `string=` cleanup

Applies when: removing `<field name=".." string="X">` from XML views when the
model's own field definition (`fields.Char(..., string='X')` etc.) already has the
exact same label — Odoo auto-derives the view label from the field def, so a
matching override is dead weight. Pure attribute deletion, zero rendered behavior
change.

Parent playbook: [inherit-view](inherit-view.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] No test dispatch — there is no testable behavior change (labels
   render identically with or without the redundant attribute). Confirm this
   reasoning before skipping, don't skip silently on future runs unless the
   same "identical rendered output" property holds.
- [ ] **Run the export scanner** (do not re-implement AST/lxml by hand):
   ```bash
   odoo view-redundant-string <module-dirs-or-trees...> --check
   ```
   Pass **all** addon trees (core + standard + project) so inherited core fields
   resolve. Report-only by default; add `--dry-run` to preview `--fix` edits.
- [ ] Review hits: only exact `string=` matches on `<field>` nodes are flagged.
   Do NOT touch `<label>`, `<button>`, `<filter>`, `<separator>` (tool never
   does). Multi-line tags are reported but not auto-fixed — edit those by hand.
- [ ] Apply safe single-line removals:
   ```bash
   odoo view-redundant-string <same paths> --fix
   ```
- [ ] Re-run with `--check` — expect exit 0 / `hit_count: 0` (or only intentional
   multi-line leftovers handled manually).

## Pitfalls

- `lxml`'s `sourceline` attribute points to the wrong physical line for
  `<field>` tags whose attributes span multiple lines (the reported line can be
  off by 1-3 depending on how many attribute lines precede the match). The
  line-targeted regex pass will silently skip these — always re-run the detector
  after the automated pass and manually diff-check any remaining count > 0.
- Check `git status` (not just at task start, but again right before staging)
  for unrelated pre-existing uncommitted changes in the *same files* you're
  editing — a pure-deletion task can still land on a file that already has an
  unrelated in-progress edit mixed in. Always give review agents the real diff
  file, not just a prose "pure deletion" summary, so this kind of drift gets
  caught. Fix by staging only the intended hunk (`git apply --cached` against a
  hand-edited single-hunk patch) rather than `git add`-ing the whole file, so
  the commit stays scoped and the unrelated WIP is left untouched on disk.

## Example instance

- One run scanned the core tree, the standard addons, and the extra addons;
  166/168 redundant `string=` matches were single-line and auto-fixed by the
  regex pass, 3 multi-line cases needed manual `old_string`/`new_string` edits.
  One target file had an unrelated in-progress field addition (`legal_rep_phone`)
  mixed into it that predated this task; review caught it by diffing the
  actual git patch.
- Confirmed core-model fields are legitimate cross-module removal targets, not
  just project-local ones: `res.partner.vat` inherits `string='Tax ID'` from
  `odoo/addons/base/models/res_partner.py:ResPartner.default_get`.

## Relevant knowledge-base

- note: XML View — view label auto-derivation from the field definition's `string=`.
