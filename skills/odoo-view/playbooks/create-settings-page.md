# Create a settings page section

Applies when: a module needs a new configuration section in Settings — new options on
`res.config.settings` with their own titled block, searchable from the Settings search
bar.
Seeded from knowledge-base (note: Tạo settings) — not yet validated by an orchestrated
run.

Parent playbook: [implement-model](../../odoo-model/playbooks/implement-model.md) — alternative branch; matching this condition stops/replaces the remaining parent path.

## Usage
- used: 0 (tracking started 2026-07-10)
- last used: n/a

## Steps

- [ ] Add the option fields on a `res.config.settings` inherit; decide the storage
  backing per field (`config_parameter`, `related` to company, or explicit
  `get_values`/`set_values`) — per note: Tạo settings.
- [ ] Inherit the base settings form view and xpath a new `div.app_settings_block`
  into the settings container, with `data-key` set to the module's technical name.
- [ ] run playbook: [settings-sections](settings-sections.md) — wrap the section's fields in the required
  `o_settings_container` DOM structure.
- [ ] Verify: section visible under its app, Settings search finds the new options,
  values persist through save + reload.

## Pitfalls

- See [settings-sections.md](settings-sections.md) for the `o_settings_container` pitfall — don't duplicate
  it here.

## Relevant knowledge-base

- note: Tạo settings — required DOM structure (`app_settings_block`, `data-key`,
  `o_settings_container`), storage-backing options and `get_values`/`set_values`
  mechanics.
