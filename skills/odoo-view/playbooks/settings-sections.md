# Settings view sections

Applies when: adding new sections to the Settings page (Odoo > Settings or in a module's settings form).

Parent playbook: [create-settings-page](create-settings-page.md) — returning sub-step; resume the next parent step after this checklist.

## Usage
- used: 0
- last used: 2026-07-10

## Steps
- [ ] Wrap every new Settings section's fields in `<div class="o_settings_container">` inside the `app_settings_block`
- [ ] Include the section's `<h2>` header and the field group inside this div
- [ ] Without the div, the `<h2>` doesn't render and Settings search throws

## Pitfalls
- Missing `o_settings_container` div: heading is invisible, Settings search errors, section is inaccessible

## Example instance
```xml
<div class="o_settings_container">
  <h2>My Settings</h2>
  <div class="row" id="my_settings">
    <field name="my_setting" widget="boolean" class="oe_inline"/>
  </div>
</div>
```

## Relevant knowledge-base

- note: Tạo settings — required DOM structure (`app_settings_block`, `data-key`,
  `o_settings_container`).
