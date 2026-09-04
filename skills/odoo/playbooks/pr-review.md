# pr-review

Applies when: reviewing an Odoo merge/pull request, especially GitLab MRs where the
user provides an MR URL or asks to post findings back. Read-only unless the user
separately asks for code changes.

Entry point: [SKILL.md](../SKILL.md)

## Usage
- used: 0
- last used: 2026-07-22

## Steps

- [ ] Confirm review scope from wording ("first/full" vs "after last note"/delta); if
  ambiguous, ask one short clarification or default to full-current-MR and state that.
- [ ] Check for provider-specific credentials before generic auth (e.g. `GITLAB_TOKEN`
  if GitLab is obvious).
- [ ] Get the smallest authoritative review head first via API: current head, target
  branch, changed files, diff refs only. If API fails but authenticated git refs
  work, fetch the MR head/merge ref read-only and review `target...head` without
  blocking on comments/pipeline metadata.
- [ ] Review the actual diff before optional admin checks — defer comments, pipeline
  status, broad raw-file downloads until needed for a concrete finding or requested.
- [ ] Validate title/scope tags against the diff (e.g. `[DATA]` with no changed data/
  demo/fixture artifact needs relabeling).
- [ ] Avoid stale local inference — use API metadata (`source_project_id`,
  `source_branch`, `target_project_id`, `target_branch`, `sha`, `diff_refs`) for the
  real review head; label local refs secondary and verify against it first.
- [ ] Preserve dirty worktrees — read-only unless edits requested; don't checkout MR
  refs/rebase/reset/stash over unrelated local changes. Prefer API raw-file reads or
  `git show <ref>:<path>` when a verified ref exists.
- [ ] Do the findings pass in this session — no sub-agent dispatch. Run
  `odoo verify <changed paths> --root <root>` on the MR's changed modules
  (AST + RULES lint + `git diff --check` in one shot), then review the diff
  yourself against the pr-review checklist: project coding guideline,
  ORM/security/performance, test coverage. Prioritize blocker/should-fix findings
  plus anything the tools can't see (cross-MR context, pipeline history). Cite exact
  file/line from the MR head.
- [ ] Normalize finding paths before displaying or posting them: for addon files,
  use `<module>/<relative-file>:<line>` (for example,
  `sale/models/sale_order.py:107`). Strip absolute checkout,
  temporary-worktree, and `sources/*-addons/` prefixes; never expose `/tmp/...` or
  `file://` paths. Use repository-relative paths for files outside addon roots.
- [ ] Check CI/merge status only after the code review is underway — don't treat an
  older pipeline as proof for the current head; don't let CI lookup delay findings.
- [ ] Post back only on request — via the hosting API, always tag someone (requested
  person, else MR author), concise/actionable, include reviewed head SHA, no leaked
  credentials. Excluded findings (e.g. nits) stay out of the posted note but keep
  them in the in-chat summary.

## Pitfalls

- An MR can update mid-review — re-check metadata near the end and use the newest
  `sha`/pipeline status in the final report or posted comment.
- Don't burn time proving generic git auth when the provider is obvious from the URL
  — an existing provider token is the lower-risk path.
- `/changes` may include enough diff for a small MR, but raw affected files are
  safer for computed fields, view domains, and JS renderers.
- Don't front-load every data source — the minimum first pass is current head,
  target base, changed files, changed code context; comments/pipelines/tests are
  supporting evidence, not prerequisites.
- A passed pipeline on an older head doesn't cover a newer pushed commit — mention
  both when relevant.
- If sandboxed network access blocks API calls, rerun the same read-only request
  with elevated permissions instead of switching to guessed local refs.
- GitLab's diffs API returns `"collapsed": true` with an empty `diff` string for
  large files — not a signal the file is empty. Check `collapsed` and fetch the raw
  file to verify; two prior reviews mis-flagged 3 real files as empty/blocker
  findings before catching this.
- Check a provider token's presence with `[ -n "$GITLAB_TOKEN" ]`, never `echo` the
  value — has leaked a partial token before.

## Relevant knowledge-base

- Use `note: Odoo Fields`, `note: Common ORM Method`, `note: XML View`, or direct
  source citations only for load-bearing Odoo behavior claims found during review —
  don't copy domain mechanics into this playbook.
