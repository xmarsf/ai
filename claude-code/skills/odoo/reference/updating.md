# Updating the odoo skill suite

Read this only when a run surfaced a lesson worth keeping — a pitfall, a
correction, a new version quirk — or on an explicit ask to improve the suite.
It owns the store-routing table, the write-back loop for version quirks, and
the admission test. Not read during lesson-free task execution.

One owner per piece of information: every other store points at the owner via
a playbook call, a `compat:<id>` citation, or a note pointer — never a copy.

## Store routing

| Lesson | Owner |
| --- | --- |
| Version/API verdict with a greppable core proof | compat matrix, via `odoo compat add` (odoo-cli) |
| Ordered recurring task sequence | `playbooks/<slug>.md` in the owning skill (this router, or the task skill whose artifact it shapes) |
| Deterministic transform / check that will run again without judgment | **Export artifact** — project script, generator, odoo-cli subcommand, or hook; a playbook step may point at it, but the runnable file owns it |
| Project-specific convention (naming, commit style, review rules) | that project's own `AGENTS.md` / coding guideline |
| Odoo domain fact **without** a reproducible core proof | project-local note — not the matrix, not a playbook, and never asserted from memory |

**Zero-token bias:** if a run re-derived a procedure or fact a future session
will need again, route it through the table above before close — chat alone is
not an export. Prefer a runnable artifact over a prose step that says "figure
out X".

## Write-back loop for version quirks

1. **Locate the proof in a declared tree.** Grep the core checkout from the
   project's config (`odoo_community_path`, `odoo_enterprise_path`), using the
   per-major layout (`orm-module-layout`): `odoo/models.py` at 17/18 vs
   `odoo/orm/` at 19. No proof, no admission.
2. **`odoo compat add --id <slug> --title ... --kind ... --replacement ...
   --status-per-version 17=...,18=...,19=... --proof N=odoo/...:"PATTERN"`.**
   It validates the proof against the declared tree (refuses on mismatch),
   writes the entry as `status: candidate` with `source: session:<date>`, and
   prints the resulting diff plus the push command. Skills never hand-edit the
   matrix YAML.
3. **User action, not agent action:** the user pushes the branch and opens the
   MR on gitlab.vdx.vn (odoo-cli repo). The agent prints the command; it never
   opens the MR itself.
4. **Review promotes** the entry to `confirmed`. Until then it is a candidate:
   usable, but cited as such.
5. **`odoo compat check` keeps every proof honest** against the local trees
   afterwards (PROOF OK / LINE DRIFT / PROOF STALE).

A quirk with no reproducible core proof is **not admitted**: it stays a
project-local note in the repo where it was found.

## Playbook admission test

Create a new playbook only when **all three** pass; otherwise route the lesson
through the store-routing table line by line:

1. **Ordering** — the lesson prescribes a sequence or procedure. A bag of
   independent do/don'ts is not a playbook: each line would be a matrix entry
   (version-conditional API), a project rule, or a one-off note. Pure
   mechanical transforms (same inputs → same outputs, no judgment) → export
   artifact, not a playbook.
2. **Recurrence** — a second, genuinely different occurrence of the shape has
   happened, or the task-shape sweep makes the shared building block
   predictably recurring.
3. **Trigger** — you can write an `Applies when:` line that passes the trigger
   quality test below.

### Trigger quality test

The `Applies when:` line is the playbook's trigger: it must name signals
observable in the request or the planned diff **before** reading the playbook
body — the artifact touched (field / button / view / domain / report /
migration), a risk shape, or an error message. Two failure modes, both fatal:

- **Too broad** — fires on most tasks, or can't be ranked against other
  triggers ("computed fields or onchange handlers that interact with views,
  record state, or messaging").
- **Too narrow** — only re-matches the instance that created it (concrete
  model/field names outside an "e.g.").

### Generalization test

Before saving any new or edited playbook: substitute every concrete
model/field/module name in Steps or Pitfalls with the role it plays. If a
sentence becomes empty or meaningless, it is session narration — move it to
`## Example instance` or delete it. If you cannot state a step without naming
the exact models involved, wait for a second, genuinely different occurrence.

## Editing an existing playbook

- Don't rewrite the whole file. Append the new information where it fits: a
  pitfall under the relevant checklist item, a missing step, a split of an
  over-broad step, or a linked playbook call at the point it's needed. If the
  run proved the playbook wrong, correct the item in place rather than
  appending a contradiction.
- Extract a reusable sub-playbook only when the same chunk shows up a second
  time; replace the duplicated content with one linked call line and add the
  reverse-nav on the child (`Parent playbook:` / `Called by:`). Author parents
  with linked call lines, never by inlining a child's checklist; nested calls
  open lazily.
- Keep the `## Usage` counter edit (`used` +1, `last used` date) as the only
  per-run bookkeeping write, and only for playbooks actually followed. Never
  create audit/history prose merely to record that a check ran.

**Link, don't just name, every reference**: playbook calls use a relative
Markdown link (`run playbook: [slug](../odoo-model/playbooks/slug.md)`), never
wrapped in backticks. Cross-skill calls point into the owning task skill's
`playbooks/`.
