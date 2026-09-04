# View inheritance & XML overrides

Applies when: inheriting a view and modifying inherited fields' attributes via `<attribute>` tags.

Parent playbook: [inherit-view](inherit-view.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0
- last used: 2026-07-10

## Steps
- [ ] Use `position=attributes`; verify add/remove/replace semantics in `note: XML View - Attribute Add Remove & Widgets`.
- [ ] Apply `domain=` at every intended view surface; verify the combined architecture and `note: Odoo domain`.

## Pitfalls
- Do not infer attribute or domain merge behavior; inspect the compiled view.

## Relevant knowledge-base

- note: XML View - Attribute Add Remove & Widgets — `<attribute add=.../>` merge
  behavior (boolean/string-list only).
- note: Odoo domain — view-level domain vs. Python field `domain=` precedence.
