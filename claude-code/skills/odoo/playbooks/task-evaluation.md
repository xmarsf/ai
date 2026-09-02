# Task evaluation

Applies when: every Odoo development task, before analysis, test dispatch, or
implementation. Classify scope/risk, split work, choose tests, and match playbooks.

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 21
- last used: 2026-07-22

## Steps

- [ ] **Read repo rules.** Applicable `AGENTS.md` / guidelines before edits or
  dispatch; pass relevant rules to mutating agents.
- [ ] **Check current behavior.** Existing models/views/methods for the user story.
  Prefer **Explore**; one known path may be read directly.
- [ ] **Trace business-flow impact.** When the changed value or record crosses addon
  boundaries, map its producer and immediate upstream/downstream consumers before
  fixing one layer; surface any scope expansion instead of discovering it piecemeal.
- [ ] **Rate effort** and **impact** (glossary levels). Smallest fitting level.
- [ ] **Split large work** by business outcome when ≥2 of: independent acceptance
  criteria, multiple addon owners, >8 likely files, unclear migration/data impact,
  unrelated playbook shapes, separately shippable items. **Batch** XS/low same-shape
  cleanup when useful; do not widen explicit user scope.
- [ ] **List sub-tasks.** One business outcome each; keep field/view/backfill visible
  inside large features. Resplit unrelated shapes.
- [ ] **Match playbooks (top-level only — lazy expansion).** Per sub-task:
  1. Broad shapes in [SKILL.md](../SKILL.md).
  2. Task patterns in the task skills' playbooks — matched by trigger/shape, not
     model name; the router [SKILL.md](../SKILL.md) dispatch table picks the
     skill, and that skill's SKILL.md holds its own playbook index.
  3. **Parent precedence:** if a parent broad shape would expand the same children
     that also match the raw request, match **only the parent** at step 0. Put
     children in `expand-when` (do not peer-match parent + children). Examples:
     host field + bulk wizard → match `implement-model`, expand-when
     `implement-field` + `implement-wizard`; archive/soft-delete on a model →
     match `implement-model` or `implement-field`, expand-when
     `add-active-field-archive`; **field/method on a model defined elsewhere via
     this module’s `_inherit`** → match `implement-model` (not bare
     `implement-field`), expand-when `inherit-model` + `implement-field` (+ view
     child as needed).
  4. Read matched **top-level** playbooks only; nested → plan as
     `expand-when: <condition>` (do not open yet). Log bare slugs (no `.md`).
  5. Merge top-level checklists; tag steps by source.
  6. Record `no matching playbook` when none fits.
  7. Re-check for likely nested shapes (constraints, object buttons, archive,
     multi-hop domains, `_inherit` extensions) as more **expand-when** candidates —
     still unread. Archive / soft-delete → ensure `add-active-field-archive` is
     expand-when if not already covered by a matched parent step. Foreign-model
     `_inherit` work → ensure `inherit-model` is expand-when under `implement-model`.
  8. Bad trigger line → use the file's `Applies when:`; flag the index that
     carries it for repair.
- [ ] **Choose test strategy + test surface.**
  - **TDD path** for **business behavior**; **module-update path** for
    **declarative UI / schema work**. Classify by behavior, not file type.
  - High-impact business behavior defaults to TDD; record exceptions.
  - On TDD: plan `expand-when: write-odoo-tests` (fires
    **mandatory** nested `test-case-selection` before `odoo-tdd` dispatch — see
    [write-odoo-tests](../odoo-test/playbooks/write-odoo-tests.md) hard gate). At evaluation time only
    note expand-when; **do not open nested yet** unless this task is pure testing.
    Step 3 of SKILL must open selection and finish a **case table** before type
    choice / tdd spawn. Multi-addon → also `expand-when: test-cross-module`
    ([test-cross-module](../odoo-test/playbooks/test-cross-module.md)).
  - **Test surface** drives **tdd tier** (surface beats effort) — glossary.
- [ ] **Zero-token check** (infer once / export / run free — see [SKILL.md](../SKILL.md)).
  Prefer `python3 …/scripts/oo.py zero-token --n-similar N […]` (or the package
  inside `oo pipeline eval`) and record its `export_plan` in the working plan. Manual
  equivalent:
  1. **Already captured?** A matched playbook, RULES line, vault note, or existing
     project script/helper already owns this shape → plan *follow/extend*, not
     re-derive. Prefer Common/`_make_*` / shared helpers over new one-off fixtures.
  2. **N× same shape?** ≥2 near-identical artifacts (fields, views, ACL rows,
     migration transforms, boilerplate tests) → set `export_plan`: one pattern
     (generator, template, helper, or single authoritative draft) then apply N times.
     Do **not** plan N separate inference designs.
  3. **Deterministic verify?** Tests/lint/module-update/no-translate → plan tool
     runs, not agent reasoning loops about expected outcome.
  4. **Skip export** when still prototyping or each instance needs distinct judgment.
- [ ] **Process catalog (optional but preferred).** `oo pipeline match` / `oo pipeline catalog` for
  top-level candidates; confirm triggers yourself. Do not bulk-read every playbook.
- [ ] **Choose pipeline_depth** (`cheap` / `normal` / `full`) per glossary +
  [SKILL.md](../SKILL.md) branch exits. Cheap is default when it matches — no confirm ask.
  Force **`full`** when the task pairs `res.config.settings` / `ir.config_parameter`
  with a create/write (or other runtime) behavior change on a business model, or when
  multi-addon / security / migration / high-impact criteria already apply.
- [ ] **Validate dispatch.** Note worktree state; ensure test package exists when TDD.
  User approval only for nontrivial unapproved design — not routine cheap skips.
  Do not dispatch an LLM agent for work a script or matched playbook already
  executes deterministically.
- [ ] **Record evaluation** in the **working plan** (effort, impact, pipeline_depth,
  split/batch, sub-tasks, top-level playbooks, expand-when, strategy, surface,
  case-table expand-when / later finished table, owner module, odoo-tdd model,
  `export_plan` or `export_plan: none`, main risk). Pass unchanged to specialists
  when they run.

## Default action

| Effort | Default |
| ------ | ------- |
| `XS`   | Prefer **cheap path** when module-update-only; batch if useful. |
| `S`    | Cheap if module-update-only + low impact; else **normal** + TDD only for behavior. |
| `M`    | Normal; TDD for behavior, module update for declarative UI. |
| `L`    | **Full**; explicit scope; consider splitting. |
| `XL`   | Full; stop and propose a breakdown. |

## Pitfalls

- Diff size ≠ risk — do not pick cheap when impact is medium/high.
- Split by business outcome, not file type.
- Manual repro ≠ regression test for business behavior.
- No odoo-tdd for pure declarative field/view/translation — module update only.
- No eager nested expansion at step 0.
- Peer-matching `implement-field` + `implement-wizard` when `implement-model` is the
  real parent — breaks diamond expand-once and misses model-level steps.
- Under-classifying **test surface** worse than over-classifying effort.
- Large wording can hide nested shapes — list as expand-when, not pre-reads.
- Skipping case ownership (re-testing dependency modules) wastes suite time — record covered-elsewhere cites.
- Hand-planning N near-copies without `export_plan` — burns tokens and drifts; infer once then apply.
- Re-deriving a matched playbook's sequence "from experience" instead of opening it.

## Relevant knowledge-base

- Pointers only when evaluation itself needs a domain fact.
