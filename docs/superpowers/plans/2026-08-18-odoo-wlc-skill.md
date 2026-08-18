# odoo-wlc Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `~/.claude/skills/odoo-wlc` — a self-contained, manually-triggered Claude skill that runs the full Odoo Weblate translation round-trip (report untranslated → download `.po` → Claude translates → validate → upload → commit → push) and ends by returning the GitLab merge-request URL.

**Architecture:** Skill = agent-facing `SKILL.md` orchestration doc + stdlib-only Python tools. `po_ops.py` parses/fills/validates gettext `.po` without external libs (guaranteed msgid integrity via JSON round-trip, never direct `.po` editing). `weblate_api.py` reads auth from `~/.weblate`, queries Weblate REST for untranslated statistics and `push_branch` (wlc 2.1.1 CLI omits it), and constructs the fallback MR URL. `wlc` CLI handles download/upload/commit/push. Weblate server runs the `GitLab merge request` VCS backend, so `wlc push` normally creates the MR server-side; skill parses the URL from push output, falling back to a constructed `merge_requests/new?...` URL.

**Tech Stack:** Python 3 stdlib only (argparse, configparser, json, re, urllib.request), `wlc` 2.1.1 (project venv), Weblate REST API, pytest for tool tests.

**Spec:** Workflow doc `/home/xmars/dev/vdx-vn/g10-qms/addons/translation-with-weblate.md` + decisions locked in grilling session 2026-08-18 (table in plan discussion, reproduced under Global Constraints).

## Global Constraints

- Skill lives at `~/.claude/skills/odoo-wlc/` and is **fully self-contained**: all scripts, reference docs, and the glossary ship inside the skill dir. Zero dependency on any project's layout (no `translation-work/tools` imports).
- Python scripts use **stdlib only** — no polib, no requests, no pip installs for the skill itself.
- Default language `vi`; any other lang passed as arg works but gets no glossary aid.
- Auth comes exclusively from `~/.weblate` (`[weblate] url` + `[keys]` section; option name under `[keys]` equals the `url` value exactly) or `WLC_URL`/`WLC_KEY` env. Server URL is never a CLI flag.
- Never edit `.po`/`.pot` files directly in the source repo — translation changes go through Weblate upload and land via the GitLab MR (rule from spec doc).
- `msgid` values must remain untouched; placeholders (`%s`, `%d`, `%(...)s`, `%%`, `\n`, `\t`, XML tags in views) must match msgid exactly. Enforced mechanically by `po_ops.py check`.
- One review gate per invocation: translate all selected components, show summary + diffs, wait for user approval, then upload all → `wlc commit` per component → single project-wide `wlc push` → MR URL.
- Verification before upload is local only: po integrity + placeholder match + non-empty msgstr. No Odoo DB import.
- The skill is manually triggered (`/odoo-wlc [component...] [lang]`). With no component args it reports untranslated counts per component and asks which to process.
- Known server facts (may10-odoo-qms, verified live 2026-08-18): Weblate `https://translate.vdx.vn/api/`, project slug `may10-odoo-qms`, components like `g10-access-management` (slug = module name with `-`), component `repo` = `https://gitlab.vdx.vn/may10/odoo-qms.git`, `branch` = `dev`, `push_branch` = `weblate-translations`, `vcs` = `gitlab` (MR backend).
- `~/.claude` is not a git repo — skill files cannot be committed; each task ends with a verification step instead of a commit step. Only this plan doc is committed (in `xmarsf/ai`).
- `wlc` may not be on PATH (it lives in project venv, e.g. `venv3.12/bin/wlc`). Skill resolves it: `which wlc` → else first `venv*/bin/wlc` in project root → else instruct `pip install wlc` and abort.

## File Structure

```
~/.claude/skills/odoo-wlc/
├── SKILL.md                  # frontmatter + full agent workflow (Task 7)
├── scripts/
│   ├── po_ops.py             # po parse / dump-untranslated / apply / check (Tasks 2-5)
│   └── weblate_api.py        # ~/.weblate auth, stats, push-branch, fallback MR URL (Task 6)
├── reference/
│   ├── translation-flow.md   # adapted from g10-qms spec doc (Task 1)
│   └── glossary.tsv          # seeded from g10 222K glossary, 4 cols: count/msgid/msgstr/modules (Task 1)
└── tests/
    ├── test_po_ops.py        # Tasks 2-5
    └── test_weblate_api.py   # Task 6
```

Responsibilities: `po_ops.py` owns all gettext-file mechanics (pure functions over file paths, no network). `weblate_api.py` owns all network + auth + URL construction (no po parsing). `SKILL.md` owns orchestration, the review gate, failure recovery, and the final MR-URL deliverable — it contains no logic, only `wlc`/script invocations and decision rules.

Workdir for staged files: `/tmp/odoo-wlc/<project>/<component>/` — ephemeral; diffs are shown in chat at the review gate.

---

### Task 1: Scaffold skill dir, seed reference assets

**Files:**
- Create: `~/.claude/skills/odoo-wlc/SKILL.md` (stub; full content in Task 7)
- Create: `~/.claude/skills/odoo-wlc/reference/translation-flow.md`
- Create: `~/.claude/skills/odoo-wlc/reference/glossary.tsv` (copy)
- Create: `~/.claude/skills/odoo-wlc/scripts/`, `~/.claude/skills/odoo-wlc/tests/`

**Interfaces:**
- Consumes: `/home/xmars/dev/vdx-vn/g10-qms/addons/translation-with-weblate.md` (source spec), `/home/xmars/dev/vdx-vn/g10-qms/translation-work/glossary.tsv` (seed)
- Produces: directory layout Tasks 2-7 write into

- [ ] **Step 1: Create directories**

```bash
mkdir -p ~/.claude/skills/odoo-wlc/{scripts,reference,tests}
```

- [ ] **Step 2: Write SKILL.md stub**

Write `~/.claude/skills/odoo-wlc/SKILL.md`:

```markdown
---
name: odoo-wlc
description: >-
  Odoo Weblate translation round-trip via wlc. Use when translating Odoo module
  .po files through Weblate (translate.vdx.vn style setups), pushing translations
  to GitLab via merge request, or when the user says "translate modules",
  "weblate", "wlc", or invokes /odoo-wlc. Manually triggered by design.
---

# odoo-wlc — Odoo Weblate translation pipeline

Full workflow doc: see Task 7 (this stub is replaced then).
```

- [ ] **Step 3: Seed reference/translation-flow.md**

Copy the spec doc, then append a "Server facts" section so the skill carries its own reference (verbatim from Global Constraints):

```bash
cp /home/xmars/dev/vdx-vn/g10-qms/addons/translation-with-weblate.md \
   ~/.claude/skills/odoo-wlc/reference/translation-flow.md
```

Append to that file:

```markdown

## Server facts (verified 2026-08-18, may10-odoo-qms)

- Weblate API root: from `~/.weblate` `[weblate] url` (currently `https://translate.vdx.vn/api/`).
- Component `repo`: `https://gitlab.vdx.vn/may10/odoo-qms.git`, `branch`: `dev`, `push_branch`: `weblate-translations`, `vcs`: `gitlab` (GitLab merge request backend).
- `wlc show` does NOT print `push_branch` (wlc 2.1.1 omits it). Use `scripts/weblate_api.py push-branch` instead.
- With the GitLab MR backend, `wlc push` makes the Weblate server open the MR itself; its output contains the MR URL.
```

- [ ] **Step 4: Seed glossary**

```bash
cp /home/xmars/dev/vdx-vn/g10-qms/translation-work/glossary.tsv \
   ~/.claude/skills/odoo-wlc/reference/glossary.tsv
```

- [ ] **Step 5: Verify**

```bash
find ~/.claude/skills/odoo-wlc -type f | sort
head -3 ~/.claude/skills/odoo-wlc/reference/glossary.tsv   # expect: count<TAB>msgid<TAB>msgstr<TAB>modules
grep -c 'Server facts' ~/.claude/skills/odoo-wlc/reference/translation-flow.md  # expect: 1
```

Expected: 3 files listed (SKILL.md, translation-flow.md, glossary.tsv) + 2 empty dirs.

---

### Task 2: po core — entry splitting, unquote/requote

**Files:**
- Create: `~/.claude/skills/odoo-wlc/scripts/po_ops.py`
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`

**Interfaces:**
- Consumes: nothing (first code task)
- Produces (imported by Tasks 3-5 and used by tests):
  - `split_entries(text: str) -> list[list[str]]` — splits raw po text into entries (list of raw lines, comments included); an entry starts at the first comment/keyword line after a blank line
  - `entry_field(lines: list[str], field: str) -> str | None` — concatenated unquoted value of `msgid`/`msgstr`/`msgctxt` for an entry (multiline continuation included), `None` if absent
  - `po_unquote(parts: list[str]) -> str` — po quoted string parts → decoded string
  - `po_quote(s: str) -> str` — string → one quoted po literal (with `"` framing, escapes `\` `"` and real newlines/tabs as `\n` `\t`)
  - `is_untranslated(lines: list[str]) -> bool` — entry has empty msgstr, is not fuzzy (`#, fuzzy`), not obsolete (`#~`), and has no `msgid_plural`

- [ ] **Step 1: Write the failing test**

Create `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from po_ops import split_entries, entry_field, po_unquote, po_quote, is_untranslated

FIXTURE = '''#. module: g10_master
#: model:ir.model.fields,field_description:g10_master.field_g10_production__name
msgid "Production Name"
msgstr ""

#. module: g10_master
#: code:models/production.py:0
msgid ""
"Multi line with %%s placeholder and \\\"quotes\\\"\\n"
"second line"
msgstr "Tạo vào"

#: model:ir.ui.view,arch_db:g10_master.view_form
msgid "Batch <b>number</b> %(_batch)s"
msgstr "Số lô"

#, fuzzy
msgid "Fuzzy one"
msgstr ""

#~ msgid "Obsolete"
#~ msgstr "Cũ"
'''

def test_split_entries_count():
    entries = split_entries(FIXTURE)
    assert len(entries) == 5

def test_entry_field_simple():
    entries = split_entries(FIXTURE)
    assert entry_field(entries[0], "msgid") == "Production Name"
    assert entry_field(entries[0], "msgstr") == ""

def test_entry_field_multiline():
    entries = split_entries(FIXTURE)
    assert entry_field(entries[1], "msgid") == 'Multi line with %s placeholder and "quotes"\nsecond line'

def test_entry_field_missing():
    entries = split_entries(FIXTURE)
    assert entry_field(entries[0], "msgctxt") is None

def test_untranslated():
    entries = split_entries(FIXTURE)
    assert is_untranslated(entries[0]) is True          # empty msgstr
    assert is_untranslated(entries[1]) is False         # has msgstr
    assert is_untranslated(entries[3]) is False         # fuzzy
    assert is_untranslated(entries[4]) is False         # obsolete

def test_quote_roundtrip():
    s = 'a "b" \\ c\nd\te'
    assert po_unquote([po_quote(s)]) == s
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'po_ops'`.

- [ ] **Step 3: Write minimal implementation**

Create `~/.claude/skills/odoo-wlc/scripts/po_ops.py`:

```python
#!/usr/bin/env python3
"""gettext .po operations for the odoo-wlc skill. Stdlib only.

PO parsing model: a file is a sequence of entries; an entry is the raw list of
lines (comments + keyword lines) between blank separators. We never rewrite a
file wholesale — `apply` copies raw lines and replaces only msgstr lines, so
msgid text and formatting are preserved byte-for-byte.
"""
import re

KEYWORD_RE = re.compile(r'^(msgctxt|msgid|msgid_plural|msgstr(?:\[\d+\])?)\s+(.*)$')


def split_entries(text):
    """Split raw po text into entries (lists of raw lines, newline-stripped)."""
    entries, current = [], []
    for line in text.splitlines():
        if line.strip() == '':
            if current:
                entries.append(current)
                current = []
        else:
            current.append(line)
    if current:
        entries.append(current)
    return entries


def _string_parts(lines, field):
    """Quoted string parts for `field` across the entry (first match + continuations)."""
    parts, capturing = [], False
    for line in lines:
        m = KEYWORD_RE.match(line)
        if m:
            capturing = m.group(1) == field
            if capturing:
                parts.append(m.group(2).strip())
        elif capturing and line.lstrip().startswith('"'):
            parts.append(line.strip())
    return parts


def po_unquote(parts):
    """['"a\\nb"'] -> 'a\nb' (real newline). Handles \\\\ \\" \\n \\t."""
    joined = ''.join(p[1:-1] for p in parts if len(p) >= 2)
    out, i = [], 0
    while i < len(joined):
        c = joined[i]
        if c == '\\' and i + 1 < len(joined):
            nxt = joined[i + 1]
            out.append({'n': '\n', 't': '\t', '\\': '\\', '"': '"'}.get(nxt, '\\' + nxt))
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def po_quote(s):
    """String -> single po quoted literal (no wrapping; valid, if long)."""
    escaped = (s.replace('\\', '\\\\').replace('"', '\\"')
                .replace('\n', '\\n').replace('\t', '\\t'))
    return '"%s"' % escaped


def entry_field(lines, field):
    parts = _string_parts(lines, field)
    if not parts:
        return None
    return po_unquote(parts)


def is_untranslated(lines):
    if any(line.startswith('#~') for line in lines):
        return False
    if any(line.strip() == '#, fuzzy' for line in lines):
        return False
    if entry_field(lines, 'msgid_plural') is not None:
        return False
    msgid = entry_field(lines, 'msgid') or ''
    if msgid == '':           # header entry
        return False
    msgstr = entry_field(lines, 'msgstr')
    return msgstr == ''
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Verify** (substitutes for commit — skill dir is not a git repo)

```bash
grep -c 'def ' ~/.claude/skills/odoo-wlc/scripts/po_ops.py   # expect: 6
```

---

### Task 3: `stats` and `dump` subcommands

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/scripts/po_ops.py` (add `_main`, subcommands)
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py` (append)

**Interfaces:**
- Consumes: Task 2 functions
- Produces (used by SKILL.md workflow, Task 7):
  - CLI: `po_ops.py stats FILE` → stdout JSON `{"total": int, "untranslated": int}`
  - CLI: `po_ops.py dump FILE` → stdout JSON `{"entries": [{"key": str, "msgid": str, "msgstr": "", "locations": [str], "comments": [str]}]}` — only untranslated entries, file order. `key` = `msgctxt + "\x04" + msgid` when msgctxt exists else `msgid` (gettext lookup convention; `apply` keys on it).

- [ ] **Step 1: Write the failing tests**

Append to `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
import json, subprocess

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "po_ops.py")
FIXTURE_FILE = "/tmp/test_odoo_wlc_fixture.po"


def _write_fixture():
    Path(FIXTURE_FILE).write_text(FIXTURE, encoding="utf-8")


def test_stats_cli():
    _write_fixture()
    out = subprocess.run([sys.executable, SCRIPT, "stats", FIXTURE_FILE],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == {"total": 3, "untranslated": 1}


def test_dump_cli():
    _write_fixture()
    out = subprocess.run([sys.executable, SCRIPT, "dump", FIXTURE_FILE],
                         capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    assert len(data["entries"]) == 1
    e = data["entries"][0]
    assert e["key"] == "Production Name"
    assert e["msgid"] == "Production Name"
    assert e["msgstr"] == ""
    assert any("field_description" in loc for loc in e["locations"])
```

Note: `total` counts non-obsolete, non-header entries (3 = simple + multiline + Batch; fuzzy and obsolete excluded).

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 2 new FAIL (`SystemExit` / `check=True` CalledProcessError — subcommands don't exist yet).

- [ ] **Step 3: Implement subcommands**

Append to `~/.claude/skills/odoo-wlc/scripts/po_ops.py`:

```python
def entry_key(lines):
    msgctxt = entry_field(lines, 'msgctxt')
    msgid = entry_field(lines, 'msgid')
    return (msgctxt + '\x04' + msgid) if msgctxt is not None else msgid


def collect_meta(lines):
    locations = [l[2:].strip() for l in lines if l.startswith('#:')]
    comments = [l[l.index(' ') + 1:].strip() for l in lines
                if l.startswith('#.') or l.startswith('# ')]
    return locations, comments


def cmd_stats(path):
    text = open(path, encoding='utf-8').read()
    entries = [e for e in split_entries(text) if not any(l.startswith('#~') for l in e)]
    entries = [e for e in entries if (entry_field(e, 'msgid') or '') != '']
    untranslated = sum(1 for e in entries if is_untranslated(e))
    return {"total": len(entries), "untranslated": untranslated}


def cmd_dump(path):
    text = open(path, encoding='utf-8').read()
    out = []
    for e in split_entries(text):
        if not is_untranslated(e):
            continue
        locations, comments = collect_meta(e)
        out.append({"key": entry_key(e),
                    "msgid": entry_field(e, 'msgid'),
                    "msgstr": "",
                    "locations": locations,
                    "comments": comments})
    return {"entries": out}


def main(argv=None):
    import argparse, json as _json
    p = argparse.ArgumentParser(prog='po_ops.py')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('stats').add_argument('file')
    sub.add_parser('dump').add_argument('file')
    ap = sub.add_parser('apply')
    ap.add_argument('orig')
    ap.add_argument('filled')
    ap.add_argument('-o', '--output', required=True)
    ck = sub.add_parser('check')
    ck.add_argument('orig')
    ck.add_argument('new')
    args = p.parse_args(argv)
    if args.cmd == 'stats':
        print(_json.dumps(cmd_stats(args.file), ensure_ascii=False))
    elif args.cmd == 'dump':
        print(_json.dumps(cmd_dump(args.file), ensure_ascii=False))
    elif args.cmd == 'apply':
        print(_json.dumps(cmd_apply(args.orig, args.filled, args.output), ensure_ascii=False))
    elif args.cmd == 'check':
        report = cmd_check(args.orig, args.new)
        print(_json.dumps(report, ensure_ascii=False))
        raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
```

(`apply`/`check` referenced in argparse now; implemented Tasks 4-5. To keep this task green, add temporary stubs and delete them in the next tasks — or accept that calling them errors; tests for them don't exist yet, argparse merely registers them.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Verify CLI manually**

```bash
printf 'msgid "A"\nmsgstr ""\n\nmsgid "B"\nmsgstr "Bà"\n' > /tmp/po_smoke.po
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py stats /tmp/po_smoke.po   # {"total": 2, "untranslated": 1}
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py dump /tmp/po_smoke.po    # one entry, key "A"
```

---

### Task 4: `apply` subcommand — JSON back into `.po`

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/scripts/po_ops.py` (`cmd_apply`)
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py` (append)

**Interfaces:**
- Consumes: Task 2 functions, Task 3 `entry_key`
- Produces: CLI `po_ops.py apply ORIG FILLED_JSON -o OUT_PO` → stdout JSON `{"applied": int, "skipped_unknown_keys": [str]}`. Filled format: `{"entries": [{"key": str, "msgstr": str}]}`. Raw msgid lines, comments, locations, and all other entries are copied byte-identical; only the `msgstr` line of matched untranslated entries is replaced with `msgstr "..."` (single line, po_quote escaping). Empty-string msgstr in input = leave entry untouched (lets Claude mark not-yet-sure terms) and counts under `applied` only when non-empty.

- [ ] **Step 1: Write the failing tests**

Append to `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
def test_apply_cli_roundtrip():
    _write_fixture()
    filled = {"entries": [{"key": "Production Name", "msgstr": "Tên sản lượng"}]}
    Path("/tmp/test_filled.json").write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([sys.executable, SCRIPT, "apply", FIXTURE_FILE,
                          "/tmp/test_filled.json", "-o", "/tmp/test_out.po"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == {"applied": 1, "skipped_unknown_keys": []}
    orig = Path(FIXTURE_FILE).read_text(encoding="utf-8")
    new = Path("/tmp/test_out.po").read_text(encoding="utf-8")
    assert 'msgid "Production Name"' in new            # msgid untouched
    assert 'msgstr "Tên sản lượng"' in new             # msgstr filled
    assert 'Tạo vào' in new                            # other entries preserved
    assert new.count('field_description') == orig.count('field_description')  # locations intact


def test_apply_skips_unknown_key():
    _write_fixture()
    filled = {"entries": [{"key": "No Such Term", "msgstr": "X"}]}
    Path("/tmp/test_filled.json").write_text(json.dumps(filled), encoding="utf-8")
    out = subprocess.run([sys.executable, SCRIPT, "apply", FIXTURE_FILE,
                          "/tmp/test_filled.json", "-o", "/tmp/test_out.po"],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["applied"] == 0
    assert json.loads(out.stdout)["skipped_unknown_keys"] == ["No Such Term"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 2 new FAIL (cmd_apply missing / CalledProcessError).

- [ ] **Step 3: Implement cmd_apply**

Insert above `main` in `~/.claude/skills/odoo-wlc/scripts/po_ops.py`:

```python
def cmd_apply(orig_path, filled_path, out_path):
    text = open(orig_path, encoding='utf-8').read()
    filled = json.load(open(filled_path, encoding='utf-8'))['entries']
    by_key = {e['key']: e['msgstr'] for e in filled if e.get('msgstr')}
    applied, skipped = 0, [e['key'] for e in filled
                           if e['key'] not in () and not e.get('msgstr') is None]
    # simpler: track keys present in po
    seen = set()
    out_lines = []
    for entry in split_entries(text):
        key = entry_key(entry) if not any(l.startswith('#~') for l in entry) else None
        if key in by_key and is_untranslated(entry):
            seen.add(key)
            replaced = False
            for line in entry:
                if not replaced and line.startswith('msgstr'):
                    out_lines.append('msgstr ' + po_quote(by_key[key]))
                    replaced = True
                else:
                    out_lines.append(line)
            applied += 1
            out_lines.append('')      # keep blank separator
        else:
            out_lines.extend(entry)
            out_lines.append('')
    open(out_path, 'w', encoding='utf-8').write('\n'.join(out_lines) + '\n')
    skipped_unknown = [e['key'] for e in filled if e['key'] not in seen]
    return {"applied": applied, "skipped_unknown_keys": skipped_unknown}
```

Import `json` at module top (Task 2 file header): add `import json` next to `import re`. Delete the placeholder `skipped` scratch line if copied — final implementation must not contain it.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Verify whitespace fidelity**

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py apply /tmp/po_smoke.po <(echo '{"entries":[{"key":"A","msgstr":"À"}]}') -o /tmp/po_applied.po
diff <(grep -c '' /tmp/po_smoke.po) <(grep -c '' /tmp/po_applied.po) && echo SAME_LINE_COUNT
```

---

### Task 5: `check` subcommand — integrity + placeholders

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/scripts/po_ops.py` (`cmd_check`)
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py` (append)

**Interfaces:**
- Consumes: Task 2 functions
- Produces: CLI `po_ops.py check ORIG NEW` → stdout JSON report, exit 0 when `ok` else 1. Report: `{"ok": bool, "msgid_mismatch": [keys], "placeholder_mismatch": [{"key": k, "msgid_tokens": [...], "msgstr_tokens": [...]}], "empty_msgstr": [keys], "parse_ok": bool}`. Placeholder tokens = sorted multiset of regex matches `r'%(?:\([^)]*\))?[sd]|%[sd]|%%|\\n|\\t|<[^>]+>'` compared msgid vs msgstr per translated entry. Check runs over ALL non-obsolete entries of NEW (translated before + newly), msgid set compared against ORIG.

- [ ] **Step 1: Write the failing tests**

Append to `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
def test_check_pass():
    _write_fixture()
    filled = {"entries": [{"key": "Production Name", "msgstr": "Tên sản lượng"}]}
    Path("/tmp/test_filled.json").write_text(json.dumps(filled, ensure_ascii=False), encoding="utf-8")
    subprocess.run([sys.executable, SCRIPT, "apply", FIXTURE_FILE,
                    "/tmp/test_filled.json", "-o", "/tmp/test_out.po"], check=True)
    out = subprocess.run([sys.executable, SCRIPT, "check", FIXTURE_FILE, "/tmp/test_out.po"],
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert json.loads(out.stdout)["ok"] is True


def test_check_catches_placeholder_and_msgid_damage():
    bad = '''msgid "Report %s of %d items\\n"
msgstr "Báo cáo %d của %d mục\\n"

msgid "Batch <b>number</b>"
msgstr "Số lô"

msgid "Mutated"
msgstr "Đã sửa"
'''
    Path("/tmp/test_bad_new.po").write_text(bad, encoding="utf-8")
    orig = 'msgid "Report %s of %d items\\n"\nmsgstr ""\n\nmsgid "Batch <b>number</b>"\nmsgstr ""\n'
    Path("/tmp/test_bad_orig.po").write_text(orig, encoding="utf-8")
    out = subprocess.run([sys.executable, SCRIPT, "check", "/tmp/test_bad_orig.po", "/tmp/test_bad_new.po"],
                         capture_output=True, text=True)
    report = json.loads(out.stdout)
    assert out.returncode == 1
    assert report["ok"] is False
    assert len(report["placeholder_mismatch"]) == 2   # %s/%d swap + missing <b></b>
    assert "Mutated" in report["msgid_mismatch"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 2 new FAIL.

- [ ] **Step 3: Implement cmd_check**

Insert above `main` in `~/.claude/skills/odoo-wlc/scripts/po_ops.py`:

```python
PLACEHOLDER_RE = re.compile(r'%(?:\([^)]*\))?[sd]|%[sd]|%%|\\n|\\t|<[^>]+>')


def _ph_tokens(s):
    return sorted(PLACEHOLDER_RE.findall(s))


def _translated_map(path):
    text = open(path, encoding='utf-8').read()
    result = {}
    for e in split_entries(text):
        if any(l.startswith('#~') for l in e):
            continue
        msgid = entry_field(e, 'msgid')
        if msgid in (None, ''):
            continue
        result[entry_key(e)] = (msgid, entry_field(e, 'msgstr') or '')
    return result


def cmd_check(orig_path, new_path):
    orig, new = _translated_map(orig_path), _translated_map(new_path)
    mismatch = [k for k in new if k in orig and new[k][0] != orig[k][0]]
    mismatch += [k for k in orig if k not in new]
    placeholder, empty = [], []
    for k, (msgid, msgstr) in new.items():
        if msgstr == '' and k in orig and orig[k][1] == '' and not is_untranslated_split(new_path, k):
            continue  # still-untranslated entries (pre-existing) are not errors
        if msgstr == '':
            continue  # pre-existing untranslated pass through silently
        if _ph_tokens(msgid) != _ph_tokens(msgstr):
            placeholder.append({"key": k, "msgid_tokens": _ph_tokens(msgid),
                                "msgstr_tokens": _ph_tokens(msgstr)})
    ok = not mismatch and not placeholder
    return {"ok": ok, "msgid_mismatch": mismatch, "placeholder_mismatch": placeholder,
            "empty_msgstr": empty, "parse_ok": True}
```

The `is_untranslated_split` call above is wrong on purpose — do NOT keep it. Simplify to the logic actually needed (entries that were untranslated in ORIG and remain untranslated in NEW are fine; entries translated in NEW must have non-empty msgstr and matching placeholders; entries translated in ORIG that become empty in NEW are errors → append to `empty_msgstr`). Final signature:

```python
def cmd_check(orig_path, new_path):
    orig, new = _translated_map(orig_path), _translated_map(new_path)
    mismatch = [k for k in orig if k not in new or new[k][0] != orig[k][0]]
    placeholder, empty = [], []
    for k, (msgid, msgstr) in new.items():
        was_translated = k in orig and orig[k][1] != ''
        if msgstr == '' and was_translated:
            empty.append(k)
            continue
        if msgstr and _ph_tokens(msgid) != _ph_tokens(msgstr):
            placeholder.append({"key": k, "msgid_tokens": _ph_tokens(msgid),
                                "msgstr_tokens": _ph_tokens(msgstr)})
    ok = not mismatch and not placeholder and not empty
    return {"ok": ok, "msgid_mismatch": mismatch, "placeholder_mismatch": placeholder,
            "empty_msgstr": empty, "parse_ok": True}
```

Use the second version.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Verify full-suite CLI smoke**

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py check /tmp/test_bad_orig.po /tmp/test_bad_new.po; echo "exit=$?"
```

Expected: report JSON + `exit=1`.

---

### Task 6: `weblate_api.py` — auth, stats, push-branch, fallback MR URL

**Files:**
- Create: `~/.claude/skills/odoo-wlc/scripts/weblate_api.py`
- Test: `~/.claude/skills/odoo-wlc/tests/test_weblate_api.py`

**Interfaces:**
- Consumes: `~/.weblate` ini (or `WLC_URL`/`WLC_KEY`)
- Produces (used by SKILL.md workflow):
  - `load_config(path='~/.weblate') -> {"url": str, "key": str}` — `[keys]` option name must equal `url` exactly; `WLC_URL`/`WLC_KEY` env take precedence and both must be set together
  - `api_get(cfg, path) -> dict` — GET `{url}{path}` with `Authorization: Token {key}`; path starts without leading slash (e.g. `projects/may10-odoo-qms/components/`)
  - `construct_mr_url(repo, source_branch, target_branch) -> str` — `https://gitlab.vdx.vn/may10/odoo-qms/-/merge_requests/new?merge_request%5Bsource_branch%5D=...&merge_request%5Btarget_branch%5D=...`; strips userinfo (`oauth2:...@`) and `.git` suffix from repo; URL-encodes branch names
  - CLI:
    - `weblate_api.py components PROJECT` → JSON list `[{"slug": ..., "name": ...}]`
    - `weblate_api.py stats PROJECT LANG` → JSON list `[{"slug": ..., "untranslated": int, "total": int}]` (via per-component `/api/translations/P/C/LANG/statistics/`, skipping components where lang missing → `untranslated: null`)
    - `weblate_api.py push-branch PROJECT COMPONENT` → `{"repo": ..., "branch": ..., "push_branch": ...}`
    - `weblate_api.py mr-url PROJECT COMPONENT` → constructed fallback URL (uses push-branch data)

- [ ] **Step 1: Write the failing tests**

Create `~/.claude/skills/odoo-wlc/tests/test_weblate_api.py`:

```python
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import weblate_api

INI = """[weblate]
url = https://translate.vdx.vn/api/

[keys]
https://translate.vdx.vn/api/ = SECRETKEY
"""


def test_load_config_ini(tmp_path):
    ini = tmp_path / "weblate"
    ini.write_text(INI, encoding="utf-8")
    cfg = weblate_api.load_config(str(ini))
    assert cfg == {"url": "https://translate.vdx.vn/api/", "key": "SECRETKEY"}


def test_load_config_env_precedence(tmp_path, monkeypatch):
    ini = tmp_path / "weblate"
    ini.write_text(INI, encoding="utf-8")
    monkeypatch.setenv("WLC_URL", "https://env.example.com/api/")
    monkeypatch.setenv("WLC_KEY", "ENVKEY")
    cfg = weblate_api.load_config(str(ini))
    assert cfg == {"url": "https://env.example.com/api/", "key": "ENVKEY"}


def test_construct_mr_url_strips_credentials_and_git():
    url = weblate_api.construct_mr_url(
        "https://oauth2:token123@gitlab.vdx.vn/may10/odoo-qms.git",
        "weblate-translations", "dev")
    assert url == ("https://gitlab.vdx.vn/may10/odoo-qms/-/merge_requests/new"
                   "?merge_request%5Bsource_branch%5D=weblate-translations"
                   "&merge_request%5Btarget_branch%5D=dev")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_weblate_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'weblate_api'`.

- [ ] **Step 3: Implement**

Create `~/.claude/skills/odoo-wlc/scripts/weblate_api.py`:

```python
#!/usr/bin/env python3
"""Weblate REST helpers for odoo-wlc. Stdlib only; auth from ~/.weblate."""
import configparser
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def load_config(path="~/.weblate"):
    url, key = os.environ.get("WLC_URL"), os.environ.get("WLC_KEY")
    if url and key:
        return {"url": url, "key": key}
    cp = configparser.ConfigParser()
    read = cp.read(os.path.expanduser(path))
    if not read:
        raise SystemExit("error: no ~/.weblate and no WLC_URL/WLC_KEY — run wlc setup first")
    url = cp.get("weblate", "url").rstrip("/")
    for opt, val in cp.items("keys"):
        if val.strip():
            key = val.strip()
            break
    return {"url": url + "/", "key": key}


def api_get(cfg, path):
    full = cfg["url"] + path.lstrip("/")
    req = urllib.request.Request(full, headers={"Authorization": "Token " + cfg["key"]})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("error: Weblate API %s returned %s" % (full, e.code))


def construct_mr_url(repo, source_branch, target_branch):
    clean = repo.split("://", 1)[-1].split("@", 1)[-1]        # drop scheme + userinfo
    if clean.endswith(".git"):
        clean = clean[:-len(".git")]
    host, _, proj = clean.partition("/")
    q = urllib.parse.urlencode({
        "merge_request[source_branch]": source_branch,
        "merge_request[target_branch]": target_branch})
    return "https://%s/%s/-/merge_requests/new?%s" % (host, proj, q)


def cmd_components(cfg, project):
    data = api_get(cfg, "projects/%s/components/" % project)
    return [{"slug": c["slug"], "name": c["name"]} for c in data["results"]]


def cmd_stats(cfg, project, lang):
    out = []
    for comp in cmd_components(cfg, project):
        try:
            s = api_get(cfg, "translations/%s/%s/%s/statistics/" % (project, comp["slug"], lang))
            out.append({"slug": comp["slug"], "untranslated": s.get("untranslated"),
                        "total": s.get("total")})
        except SystemExit:
            out.append({"slug": comp["slug"], "untranslated": None, "total": None})
    return out


def push_branch_info(cfg, project, component):
    c = api_get(cfg, "components/%s/%s/" % (project, component))
    return {"repo": c["repo"], "branch": c["branch"], "push_branch": c.get("push_branch") or c["branch"]}


def main():
    import argparse
    p = argparse.ArgumentParser(prog="weblate_api.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("components").add_argument("project")
    st = sub.add_parser("stats"); st.add_argument("project"); st.add_argument("lang")
    pb = sub.add_parser("push-branch"); pb.add_argument("project"); pb.add_argument("component")
    mu = sub.add_parser("mr-url"); mu.add_argument("project"); mu.add_argument("component")
    args = p.parse_args()
    cfg = load_config()
    if args.cmd == "components":
        result = cmd_components(cfg, args.project)
    elif args.cmd == "stats":
        result = cmd_stats(cfg, args.project, args.lang)
    elif args.cmd == "push-branch":
        result = push_branch_info(cfg, args.project, args.component)
    else:
        info = push_branch_info(cfg, args.project, args.component)
        result = {"url": construct_mr_url(info["repo"], info["push_branch"], info["branch"])}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_weblate_api.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Live smoke against real server (read-only)**

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py push-branch may10-odoo-qms g10-access-management
# expect: {"repo": "https://gitlab.vdx.vn/may10/odoo-qms.git", "branch": "dev", "push_branch": "weblate-translations"}
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py stats may10-odoo-qms vi | head -c 400
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py mr-url may10-odoo-qms g10-access-management
# expect URL starting https://gitlab.vdx.vn/may10/odoo-qms/-/merge_requests/new?merge_request%5Bsource_branch%5D=weblate-translations
```

If `stats` 404s on statistics path, inspect `wlc --format json show may10-odoo-qms/<comp>` for the translations list URL shape and adjust the path template accordingly (server is self-hosted; version may differ from weblate.org latest).

---

### Task 7: SKILL.md — full agent workflow

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/SKILL.md` (replace stub body, keep frontmatter)

**Interfaces:**
- Consumes: Task 3-6 CLIs, `wlc`, glossary, review-gate decision rules
- Produces: the document the agent executes at `/odoo-wlc` invocation

- [ ] **Step 1: Write SKILL.md body**

Replace everything after the frontmatter with:

```markdown
# odoo-wlc — Odoo Weblate translation round-trip

Manually triggered: `/odoo-wlc [component...] [lang]`. Default lang `vi`.
Runs from an Odoo project root that has `config/project.json` (odoo-cli `setup`)
with `weblate_project`, or takes the project slug from the first argument
containing it when no config exists.

## Prerequisites (resolve first, abort with instructions if missing)

1. wlc: `WLC="$(command -v wlc || ls -d "$PWD"/venv*/bin/wlc 2>/dev/null | head -1)"`.
   Empty → tell user: `pip install wlc` into project venv, then rerun. Reuse `$WLC` for every wlc call.
2. Weblate auth: `~/.weblate` (`[keys]` section, option name == `[weblate] url` exactly,
   url ends in `/api/`) or `WLC_URL`+`WLC_KEY`. Verify: `"$WLC" show <project>`.
3. Project slug: read `config/project.json` key `weblate_project`; fallback: ask user.

## Flow

### 1. Report untranslated (no component args given)

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py stats <project> <lang>
```

Show a table: component | untranslated | total. Ask user: which components, or all.
With component args given, skip the ask.

### 2. Download per selected component

```bash
WORK=/tmp/odoo-wlc/<project>/<component>
mkdir -p "$WORK"
"$WLC" download <project>/<component>/<lang> --output "$WORK/<lang>.orig.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py stats "$WORK/<lang>.orig.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py dump "$WORK/<lang>.orig.po" > "$WORK/pending.json"
```

### 3. Translate (Claude does the translation)

For every entry in `pending.json`:
- Glossary lookup: `grep -P -i "^\d+\t<msgid-escaped>\t" ~/.claude/skills/odoo-wlc/reference/glossary.tsv`
  (escape `|()\.` for grep -P; msgid is column 2). Hit → use column 3 msgstr.
- Miss → translate yourself: Odoo/QMS domain Vietnamese, keep placeholders EXACT
  (`%s`, `%d`, `%(...)s`, `%%`, `\n`, XML tags), title-case like Odoo UI conventions.
- Location comments (`model:ir.model.fields,...` = field label, `arch_db` = view text,
  `code:` = runtime string) inform register/length.
- Ambiguous or business-critical terms → translate + flag in the review summary.
Write `{"entries": [{"key": ..., "msgstr": ...}]}` to `$WORK/filled.json` (all entries, one file per component).

### 4. Build + validate

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py apply "$WORK/<lang>.orig.po" "$WORK/filled.json" -o "$WORK/<lang>.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py check "$WORK/<lang>.orig.po" "$WORK/<lang>.po"
```

`check` exit 1 → fix reported entries (placeholder mismatches are blockers), rerun. Never upload with failing check.

### 5. Review gate (single, all components)

Present:
- Table: component | translated | warnings | glossary misses (term → proposed)
- Per component: `diff "$WORK/<lang>.orig.po" "$WORK/<lang>.po"` shown in full (msgid lines give context).

WAIT for user approval or amendments. Amend → back to step 4 for affected component.

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
   `python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py mr-url <project> <first-component>`
   and say: server may already have an open MR for this branch — check the link.
3. Print final answer: MR URL (or fallback URL) + per-component translated counts.

## Failure recovery

- `wlc upload` fails "locked" → `"$WLC" unlock <project>/<component>/<lang>`, retry once.
- `wlc push` fails (non-fast-forward / upstream moved) → `"$WLC" pull <project>`, then re-run
  step 2 (re-download, re-apply via `apply` against fresh orig — msgstrs from filled.json are reused),
  re-check, re-upload only if diffs changed, then `commit` + `push` again.
- Any Weblate API `Object not found` → wrong slug; list with
  `python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py components <project>`.

## Rules (from reference/translation-flow.md)

- Never edit `.po`/`.pot` in the source repo. Changes go: upload → Weblate commit → push → MR.
- msgid text is never modified by us; `check` enforces it.
- Cleanup: leave `/tmp/odoo-wlc/` (user may want diffs); mention path in final answer.
```

- [ ] **Step 2: Verify consistency**

Check every CLI invocation in SKILL.md matches the argparse interfaces from Tasks 3-6 exactly (`stats FILE`, `dump FILE`, `apply ORIG FILLED -o OUT`, `check ORIG NEW`, `components PROJECT`, `stats PROJECT LANG`, `push-branch PROJECT COMPONENT`, `mr-url PROJECT COMPONENT`). Read the file end to end.

```bash
grep -c 'po_ops.py\|weblate_api.py' ~/.claude/skills/odoo-wlc/SKILL.md   # expect >= 8
```

---

### Task 8: Live dry-run validation (no upload) + finalize

**Files:**
- No new files. Validates the whole chain against the real server, stopping before any mutation.

**Interfaces:**
- Consumes: everything
- Produces: verified skill, final report

- [ ] **Step 1: Pick a real component with untranslated vi terms**

```bash
WLC=/home/xmars/dev/vdx-vn/g10-qms/venv3.12/bin/wlc
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py stats may10-odoo-qms vi
```

Pick one component with `untranslated > 0`.

- [ ] **Step 2: Dry-run the pipeline (download → dump → apply with 1 real translation → check)**

```bash
WORK=/tmp/odoo-wlc/may10-odoo-qms/<component>; mkdir -p "$WORK"
"$WLC" download may10-odoo-qms/<component>/vi --output "$WORK/vi.orig.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py dump "$WORK/vi.orig.po" > "$WORK/pending.json"
# translate just ONE entry into filled.json by hand for the test
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py apply "$WORK/vi.orig.po" "$WORK/filled.json" -o "$WORK/vi.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py check "$WORK/vi.orig.po" "$WORK/vi.po"; echo "exit=$?"
```

Expected: check exit 0; `diff vi.orig.po vi.po` shows exactly one msgstr line changed; header block (msgid "") byte-identical.

- [ ] **Step 3: STOP — do not upload/push in this task.** Report results. Real upload happens on first user-invoked run.

- [ ] **Step 4: Full test suite + permissions**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/ -v    # expect 15 passed
chmod +x scripts/po_ops.py scripts/weblate_api.py
```

- [ ] **Step 5: Commit this plan doc (only artifact in a git repo)**

```bash
cd /home/xmars/dev/xmarsf/ai
git add docs/superpowers/plans/2026-08-18-odoo-wlc-skill.md
git commit -m "docs: add odoo-wlc skill implementation plan

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (workflow doc steps → tasks):
- Step 1 CI extracts pot → out of scope (GitLab CI's job; doc context only). ✔ noted in reference/translation-flow.md.
- "Check what needs translation" → Task 6 `stats` + SKILL.md §1. ✔
- Download → SKILL.md §2 (Task 7). ✔
- Translate + placeholder rules → SKILL.md §3 + enforced by Task 5 `check`. ✔
- Upload → SKILL.md §6. ✔
- Commit + push → SKILL.md §6-7. ✔
- MR URL deliverable → SKILL.md §8 + Task 6 `mr-url`. ✔
- Doc rules (no repo po edits, per-component repeat) → SKILL.md Rules. ✔
- One-time wlc setup section → SKILL.md Prerequisites + reference doc. ✔

**Locked decisions coverage:** scope A (round-trip only) ✔; placement A ✔; self-contained + glossary in skill ✔; Claude translates, single gate (SKILL.md §5) ✔; vi default + lang arg ✔; MR via push output w/ fallback (§8) ✔; component selection UX (§1) ✔; local-only verification (§4) ✔.

**Placeholder scan:** Task 5 Step 3 deliberately shows a wrong-then-correct version with instruction to use the second — final file must contain only the correct `cmd_check`. Task 4 has one scratch line flagged for deletion. No TBD/TODO elsewhere.

**Type consistency:** `entry_key`/`po_quote`/`po_unquote` names consistent across Tasks 2-5; filled.json shape `{"entries":[{"key","msgstr"}]}` identical in Task 3 (dump emits extra fields — apply reads only key/msgstr) and SKILL.md §3; CLI verbs match between Tasks 3-6 and SKILL.md grep check in Task 7.
