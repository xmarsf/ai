---
name: odoo-wlc
description: >-
  Odoo Weblate translation round-trip via wlc. Use when translating Odoo module
  .po files through a Weblate server (any wlc-backed setup), pushing translations
  to GitLab via merge request, or when the user says "translate modules",
  "weblate", "wlc", or invokes /odoo-wlc. Manually triggered by design.
---

# odoo-wlc — Odoo Weblate translation round-trip

Manually triggered: `/odoo-wlc [component...] [lang]`. Default lang `vi`.
Runs from an Odoo project root that has `config/project.json` (odoo-cli `setup`)
with `weblate_project`, or takes the project slug from the first argument
containing it when no config exists. Not tied to any specific Odoo project or
Weblate deployment — project slug, server, and glossary are all resolved at
runtime (see below).

## Resolve the skill directory first

Every script path below is written as `$SKILL_DIR/scripts/...`. Set `SKILL_DIR`
to this skill's own base directory — the directory containing this SKILL.md
(reported as "Base directory for this skill" when loaded, or find it with
`dirname` on wherever this file was read from). Do not hardcode an install
path: this skill may live under `~/.claude/skills/odoo-wlc` or be checked
into a project repo, and both must work unmodified.

## Prerequisites (resolve first, abort with instructions if missing)

1. wlc: `WLC="$(command -v wlc || ls -d "$PWD"/venv*/bin/wlc 2>/dev/null | head -1)"`.
   Empty → tell user: `pip install wlc` into project venv, then rerun. Reuse `$WLC` for every wlc call.
2. Weblate auth: `~/.weblate` (`[keys]` section, option name == `[weblate] url` exactly,
   url ends in `/api/`) or `WLC_URL`+`WLC_KEY`. Verify: `"$WLC" show <project>`.
   Auth is per-machine, not per-skill-copy — any Weblate server works, not a fixed one.
3. Project slug: read `config/project.json` key `weblate_project`; fallback: ask user.
4. GitLab auth (only needed for step 8's `find-mr` fallback): `~/.gitlab`, `[gitlab]` section,
   one `<host-url> = <token>` line per GitLab host (matched against each component's `repo`
   host). Not checked upfront — only surfaces as an error if/when step 8 needs it.

## Flow

### 1. Report untranslated (no component args given)

```bash
python3 $SKILL_DIR/scripts/weblate_api.py stats <project> <lang>
```

Show a table: component | untranslated | fuzzy | total. Rows with `null` counts have no
translation for that language yet — list them separately, don't offer them for processing.
`untranslated` is `total - translated - fuzzy` and matches what `po_ops.py stats` reports
locally; fuzzy entries are counted but NEVER touched by this skill (`dump` skips them), so
if the user wants fuzzy strings revised, that is a manual Weblate job.
Ask user: which components, or all. With component args given, skip the ask.

### 2. Download per selected component

```bash
WORK=/tmp/odoo-wlc/<project>/<component>
mkdir -p "$WORK"
"$WLC" download <project>/<component>/<lang> --output "$WORK/<lang>.orig.po"
python3 $SKILL_DIR/scripts/po_ops.py stats "$WORK/<lang>.orig.po"
python3 $SKILL_DIR/scripts/po_ops.py dump "$WORK/<lang>.orig.po" > "$WORK/pending.json"
```

Local `untranslated` must equal the API number from step 1. A mismatch means the component
changed since the report — re-run step 1 for that component before continuing.

### 3. Translate (Claude does the translation)

For every entry in `pending.json`:
- Glossary lookup (only if `$SKILL_DIR/reference/glossary.tsv` exists — it's an optional,
  project-specific term list, not bundled by default; skip this bullet entirely if absent):
  `grep -P -i "^\d+\t<msgid-escaped>\t" $SKILL_DIR/reference/glossary.tsv`
  (escape `|()\.` for grep -P; msgid is column 2). Hit → use column 3 msgstr.
  A glossary may split multi-line msgids across lines, which a line-anchored grep silently
  misses — treat those, like any no-hit term, as a miss.
- Miss (or no glossary present) → translate yourself: Odoo domain Vietnamese for the target
  module's subject matter, keep placeholders EXACT
  (`%s`, `%d`, `%(...)s`, `%%`, newlines, tabs, XML tags), title-case like Odoo UI conventions.
- Location comments (`model:ir.model.fields,...` = field label, `arch_db` = view text,
  `code:` = runtime string) inform register/length.
- Ambiguous or business-critical terms → translate anyway (best-effort msgstr), but also
  record it as a review item (see below). Genuinely unsure → emit `"msgstr": ""` for that
  key: `apply` leaves the entry untranslated instead of guessing, and it is not reported as
  an unknown key.
Write `{"entries": [{"key": ..., "msgstr": ...}]}` to `$WORK/filled.json` (all entries, one file per component).

Also write `$WORK/needs_review.json` — one entry per key that is ambiguous/business-critical,
a glossary miss, or deferred (empty `msgstr`):
`{"entries": [{"key": ..., "msgid": ..., "msgstr": ..., "reason": "ambiguous"|"glossary_miss"|"deferred"}]}`.
Empty `{"entries": []}` if nothing qualifies — still write the file, don't skip it.

### 4. Build + validate

```bash
python3 $SKILL_DIR/scripts/po_ops.py apply "$WORK/<lang>.orig.po" "$WORK/filled.json" -o "$WORK/<lang>.po"
python3 $SKILL_DIR/scripts/po_ops.py check "$WORK/<lang>.orig.po" "$WORK/<lang>.po"
```

`apply` reporting a non-empty `skipped_unknown_keys` means a key was invented or the file moved
on — re-run `dump` and rebuild `filled.json` for those keys.
`check` exit 1 → fix reported entries (placeholder and msgid mismatches are blockers), rerun.
Never upload with failing check.

### 5. Review gate (single, all components)

Present a table: component | translated | deferred (empty msgstr) | needs_review count.

Then give the user two file paths per component — do not just print a diff inline:
- **Translated file** (all applied translations): `$WORK/<lang>.po`
- **Needs-check file** (terms to review — ambiguous, glossary misses, deferred): `$WORK/needs_review.json`

Tell the user to open `needs_review.json`, correct any `msgstr` values (or fill in blanks
for deferred entries) directly in that file, and confirm when done — or confirm as-is if
no changes needed.

WAIT for user confirmation. On confirmation:
- If `needs_review.json` was edited, merge its `{key, msgstr}` pairs into `$WORK/filled.json`
  (overwrite matching keys), then go back to step 4 for that component to rebuild + re-check.
- If unchanged, proceed to step 6.

Do not proceed to step 6 for any component until its review is confirmed.

### 6. Upload + commit (after approval, every selected component)

```bash
"$WLC" upload <project>/<component>/<lang> --input "$WORK/<lang>.po"
"$WLC" commit <project>/<component>
```

### 7. Push once, project-wide

```bash
"$WLC" push <project>
```

### 8. Deliver MR URL

1. Scan push output for a URL on a line mentioning `merge request` (case-insensitive) —
   Weblate's GitLab MR backend prints the MR it created/updated. That URL is the deliverable.
2. No URL found (e.g. MR already open, output terse) →
   `python3 $SKILL_DIR/scripts/weblate_api.py find-mr <project> <first-component>`.
   This queries the GitLab API directly for the real open MR (source = component's
   `push_branch`, target = component's `branch` — always the Weblate branch merging to
   whatever the component's target branch is, e.g. `dev`), not a guessed/constructed link.
   Requires `~/.gitlab` (see Prerequisites) — if it errors, use the guidance in
   Failure recovery.
3. Print final answer: MR URL (or fallback URL) + per-component translated counts.

## Failure recovery

- `wlc upload` fails "locked" → `"$WLC" unlock <project>/<component>` (unlock is a
  component-level operation — do not pass the `/lang` suffix), retry once.
- `wlc push` fails (non-fast-forward / upstream moved) → `"$WLC" pull <project>`, then re-run
  step 2 (re-download, re-apply via `apply` against fresh orig — msgstrs from filled.json are reused),
  re-check, re-upload only if diffs changed, then `commit` + `push` again.
- Any Weblate API `Object not found` → wrong slug; list with
  `python3 $SKILL_DIR/scripts/weblate_api.py components <project>`.
- Weblate API HTTP 403 → the request lost its `User-Agent` header (server WAF rejects
  `Python-urllib/*`), not an auth problem. HTTP 401 → bad/expired token in `~/.weblate`.
- `find-mr` errors "no ~/.gitlab" or "no GitLab token for `<host>`" → add/edit `~/.gitlab`
  with a `[gitlab]` section, `<host-url> = <token>` (Personal Access Token, `api` scope, for
  that GitLab host). "no open MR `<src>` -> `<target>`" → the MR may already be merged/closed,
  or `wlc push` hasn't actually run yet — check Weblate directly for that component.

## Rules (from reference/translation-flow.md)

- Never edit `.po`/`.pot` in the source repo. Changes go: upload → Weblate commit → push → MR.
- msgid text is never modified by us; `check` enforces it.
- Fuzzy entries are out of scope; obsolete (`#~`) entries are copied through untouched.
- Cleanup: leave `/tmp/odoo-wlc/` (user may want diffs); mention path in final answer.
