# odoo-wlc Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `~/.claude/skills/odoo-wlc` — a self-contained, manually-triggered Claude skill that runs the full Odoo Weblate translation round-trip (report untranslated → download `.po` → Claude translates → validate → upload → commit → push) and ends by returning the GitLab merge-request URL.

**Architecture:** Skill = agent-facing `SKILL.md` orchestration doc + stdlib-only Python tools. `po_ops.py` parses/fills/validates gettext `.po` without external libs (guaranteed msgid integrity via JSON round-trip, never direct `.po` editing). `weblate_api.py` reads auth from `~/.weblate`, queries Weblate REST for untranslated statistics and `push_branch` (wlc 2.1.1 CLI omits it), and constructs the fallback MR URL. `wlc` CLI handles download/upload/commit/push. Weblate server runs the `GitLab merge request` VCS backend, so `wlc push` normally creates the MR server-side; skill parses the URL from push output, falling back to a constructed `merge_requests/new?...` URL.

**Tech Stack:** Python 3 stdlib only (argparse, configparser, json, re, urllib.request, concurrent.futures), `wlc` 2.1.1 (project venv), Weblate REST API, pytest for tool tests.

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
- Known server facts (may10-odoo-qms, verified live 2026-08-18): Weblate `https://translate.vdx.vn/api/`, project slug `may10-odoo-qms`, components like `g10-access-management` (slug = module name with `-`), component `repo` = `https://gitlab.vdx.vn/may10/odoo-qms.git`, `branch` = `dev`, `push_branch` = `weblate-translations`, `vcs` = `gitlab` (MR backend), 30 components on one API page.
- Server quirks that shape the code (each verified by a failing-then-passing live request): the API returns **HTTP 403 to the default `Python-urllib` User-Agent** — every request must send its own; the `[keys]` section of `~/.weblate` is keyed by URL, so `ConfigParser` must be built with `delimiters=('=',)`; and the `/statistics/` payload has **no `untranslated` field** — derive `total - translated - fuzzy`.
- Fuzzy entries are counted but never modified: `dump` skips them, so local and Weblate counts agree only when fuzzy is reported as its own column.
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
  - `po_unquote(parts: list[str]) -> str` — po quoted string parts → decoded string (escapes `\n`/`\t` become REAL newline/tab characters — Task 5's placeholder regex depends on this)
  - `po_quote(s: str) -> str` — string → one quoted po literal (with `"` framing, escapes `\` `"` and real newlines/tabs as `\n` `\t`)
  - `is_obsolete(lines) -> bool` / `is_fuzzy(lines) -> bool` — `#~` and `#, fuzzy` predicates, reused by Tasks 3-5
  - `is_untranslated(lines: list[str]) -> bool` — entry has empty msgstr, is not fuzzy, not obsolete, and has no `msgid_plural`

- [ ] **Step 1: Write the failing test**

Create `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
import json
import subprocess
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
"Multi line with %s placeholder and \\\"quotes\\\"\\n"
"second line"
msgstr ""
"Nhiều dòng với %s và \\\"trích dẫn\\\"\\n"
"dòng hai"

#: model:ir.ui.view,arch_db:g10_master.view_form
msgid "Batch <b>number</b> %(_batch)s"
msgstr "Lô <b>number</b> %(_batch)s"

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
    assert entry_field(entries[1], "msgstr") == 'Nhiều dòng với %s và "trích dẫn"\ndòng hai'


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

The fixture's already-translated entries carry the SAME placeholders as their msgids
(`%s`, the `\n`, `<b>`, `%(_batch)s`). This is required: Task 5's `check` scans every
translated entry in the file, so a fixture with placeholder-dropping translations makes
`test_check_pass` fail.

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
import json
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


def is_obsolete(lines):
    return any(line.startswith('#~') for line in lines)


def is_fuzzy(lines):
    return any(line.startswith('#,') and 'fuzzy' in line for line in lines)


def is_untranslated(lines):
    if is_obsolete(lines) or is_fuzzy(lines):
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
grep -c '^def ' ~/.claude/skills/odoo-wlc/scripts/po_ops.py   # expect: 8
```

---

### Task 3: `stats` and `dump` subcommands

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/scripts/po_ops.py` (add `_main`, subcommands)
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py` (append)

**Interfaces:**
- Consumes: Task 2 functions
- Produces (used by SKILL.md workflow, Task 7):
  - CLI: `po_ops.py stats FILE` → stdout JSON `{"total": int, "untranslated": int, "fuzzy": int}`.
    `total` = all non-obsolete entries with a real msgid (header excluded), fuzzy INCLUDED —
    this matches Weblate's own `total`, and `untranslated` then equals Weblate's
    `total - translated - fuzzy` (verified live: g10-veston-production 1015/9/9,
    g10-report 108/4/2, g10-production 337/2/0). Fuzzy is reported separately because
    `dump` deliberately skips fuzzy entries.
  - CLI: `po_ops.py dump FILE` → stdout JSON `{"entries": [{"key": str, "msgid": str, "msgstr": "", "locations": [str], "comments": [str]}]}` — only untranslated entries, file order. `key` = `msgctxt + "\x04" + msgid` when msgctxt exists else `msgid` (gettext lookup convention; `apply` keys on it).

- [ ] **Step 1: Write the failing tests**

Append to `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "po_ops.py")
FIXTURE_FILE = "/tmp/test_odoo_wlc_fixture.po"


def _write_fixture():
    Path(FIXTURE_FILE).write_text(FIXTURE, encoding="utf-8")


def _run(*args, check=True):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, check=check)


def test_stats_cli():
    _write_fixture()
    out = _run("stats", FIXTURE_FILE)
    assert json.loads(out.stdout) == {"total": 4, "untranslated": 1, "fuzzy": 1}


def test_dump_cli():
    _write_fixture()
    data = json.loads(_run("dump", FIXTURE_FILE).stdout)
    assert len(data["entries"]) == 1
    e = data["entries"][0]
    assert e["key"] == "Production Name"
    assert e["msgid"] == "Production Name"
    assert e["msgstr"] == ""
    assert any("field_description" in loc for loc in e["locations"])
```

`total` is 4: simple + multiline + Batch + fuzzy. Only the obsolete entry and the header are excluded.

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
    comments = [l[2:].strip() for l in lines
                if l.startswith('#.') or l.startswith('# ')]
    return locations, comments


def _payload_entries(text):
    """Non-obsolete entries that carry a real msgid (header excluded)."""
    return [e for e in split_entries(text)
            if not is_obsolete(e) and (entry_field(e, 'msgid') or '') != '']


def cmd_stats(path):
    """Counts aligned with Weblate: total includes fuzzy; fuzzy reported apart."""
    entries = _payload_entries(open(path, encoding='utf-8').read())
    return {"total": len(entries),
            "untranslated": sum(1 for e in entries if is_untranslated(e)),
            "fuzzy": sum(1 for e in entries if is_fuzzy(e))}


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
    import argparse
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
        print(json.dumps(cmd_stats(args.file), ensure_ascii=False))
    elif args.cmd == 'dump':
        print(json.dumps(cmd_dump(args.file), ensure_ascii=False))
    elif args.cmd == 'apply':
        print(json.dumps(cmd_apply(args.orig, args.filled, args.output), ensure_ascii=False))
    elif args.cmd == 'check':
        report = cmd_check(args.orig, args.new)
        print(json.dumps(report, ensure_ascii=False))
        raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
```

`apply`/`check` are registered in argparse now and implemented in Tasks 4-5; keep `main` at the
bottom of the file and insert the new functions above it. Calling those two subcommands before
Task 5 raises `NameError` — no test exercises them yet.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Verify CLI manually**

```bash
printf 'msgid "A"\nmsgstr ""\n\nmsgid "B"\nmsgstr "Bà"\n' > /tmp/po_smoke.po
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py stats /tmp/po_smoke.po   # {"total": 2, "untranslated": 1, "fuzzy": 0}
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py dump /tmp/po_smoke.po    # one entry, key "A"
```

---

### Task 4: `apply` subcommand — JSON back into `.po`

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/scripts/po_ops.py` (`cmd_apply`)
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py` (append)

**Interfaces:**
- Consumes: Task 2 functions, Task 3 `entry_key`
- Produces: CLI `po_ops.py apply ORIG FILLED_JSON -o OUT_PO` → stdout JSON `{"applied": int, "skipped_unknown_keys": [str]}`. Filled format: `{"entries": [{"key": str, "msgstr": str}]}`. Raw msgid lines, comments, locations, and all other entries are copied byte-identical; only the `msgstr` line of matched untranslated entries is replaced with `msgstr "..."` (single line, po_quote escaping). Entry separation is rebuilt as exactly one blank line between entries plus a single trailing newline, so the output has the same line count as the input.
- `skipped_unknown_keys` lists ONLY keys that carry a non-empty `msgstr` and were not found as an untranslated entry in ORIG. An empty `msgstr` means "Claude deferred this term": the entry is left untouched, is NOT applied, and is NOT reported as unknown.

- [ ] **Step 1: Write the failing tests**

Append to `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
def _write_filled(entries):
    Path("/tmp/test_filled.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False), encoding="utf-8")


def test_apply_cli_roundtrip():
    _write_fixture()
    _write_filled([{"key": "Production Name", "msgstr": "Tên sản lượng"}])
    out = _run("apply", FIXTURE_FILE, "/tmp/test_filled.json", "-o", "/tmp/test_out.po")
    assert json.loads(out.stdout) == {"applied": 1, "skipped_unknown_keys": []}
    orig = Path(FIXTURE_FILE).read_text(encoding="utf-8")
    new = Path("/tmp/test_out.po").read_text(encoding="utf-8")
    assert 'msgid "Production Name"' in new            # msgid untouched
    assert 'msgstr "Tên sản lượng"' in new             # msgstr filled
    assert 'Nhiều dòng với %s' in new                  # other entries preserved
    assert new.count('field_description') == orig.count('field_description')


def test_apply_preserves_line_count():
    _write_fixture()
    _write_filled([{"key": "Production Name", "msgstr": "Tên sản lượng"}])
    _run("apply", FIXTURE_FILE, "/tmp/test_filled.json", "-o", "/tmp/test_out.po")
    orig = Path(FIXTURE_FILE).read_text(encoding="utf-8")
    new = Path("/tmp/test_out.po").read_text(encoding="utf-8")
    assert new.count("\n") == orig.count("\n")         # no stray trailing blank line
    assert new.endswith('"Cũ"\n')


def test_apply_skips_unknown_key():
    _write_fixture()
    _write_filled([{"key": "No Such Term", "msgstr": "X"}])
    report = json.loads(_run("apply", FIXTURE_FILE, "/tmp/test_filled.json",
                             "-o", "/tmp/test_out.po").stdout)
    assert report["applied"] == 0
    assert report["skipped_unknown_keys"] == ["No Such Term"]


def test_apply_ignores_empty_msgstr():
    _write_fixture()
    _write_filled([{"key": "Production Name", "msgstr": ""}])
    report = json.loads(_run("apply", FIXTURE_FILE, "/tmp/test_filled.json",
                             "-o", "/tmp/test_out.po").stdout)
    assert report == {"applied": 0, "skipped_unknown_keys": []}   # deferred, not unknown
    assert 'msgid "Production Name"\nmsgstr ""' in Path("/tmp/test_out.po").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 4 new FAIL (cmd_apply missing → `NameError` → CalledProcessError).

- [ ] **Step 3: Implement cmd_apply**

Insert above `main` in `~/.claude/skills/odoo-wlc/scripts/po_ops.py`:

```python
def cmd_apply(orig_path, filled_path, out_path):
    text = open(orig_path, encoding='utf-8').read()
    filled = json.load(open(filled_path, encoding='utf-8'))['entries']
    by_key = {e['key']: e['msgstr'] for e in filled if e.get('msgstr')}
    applied, seen, blocks = 0, set(), []
    for entry in split_entries(text):
        key = None if is_obsolete(entry) else entry_key(entry)
        if key in by_key and is_untranslated(entry):
            seen.add(key)
            new_entry, replaced = [], False
            for line in entry:
                if not replaced and line.startswith('msgstr'):
                    new_entry.append('msgstr ' + po_quote(by_key[key]))
                    replaced = True
                else:
                    new_entry.append(line)
            blocks.append('\n'.join(new_entry))
            applied += 1
        else:
            blocks.append('\n'.join(entry))
    open(out_path, 'w', encoding='utf-8').write('\n\n'.join(blocks) + '\n')
    skipped = [e['key'] for e in filled if e.get('msgstr') and e['key'] not in seen]
    return {"applied": applied, "skipped_unknown_keys": skipped}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Verify whitespace fidelity**

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py apply /tmp/po_smoke.po <(echo '{"entries":[{"key":"A","msgstr":"À"}]}') -o /tmp/po_applied.po
[ "$(grep -c '' /tmp/po_smoke.po)" = "$(grep -c '' /tmp/po_applied.po)" ] && echo SAME_LINE_COUNT
diff /tmp/po_smoke.po /tmp/po_applied.po | grep -c '^[<>]'   # expect: 2 (one msgstr line swapped)
```

---

### Task 5: `check` subcommand — integrity + placeholders

**Files:**
- Modify: `~/.claude/skills/odoo-wlc/scripts/po_ops.py` (`cmd_check`)
- Test: `~/.claude/skills/odoo-wlc/tests/test_po_ops.py` (append)

**Interfaces:**
- Consumes: Task 2 functions, Task 3 `entry_key` / `_payload_entries`
- Produces: CLI `po_ops.py check ORIG NEW` → stdout JSON report, exit 0 when `ok` else 1. Report: `{"ok": bool, "msgid_mismatch": [keys], "placeholder_mismatch": [{"key": k, "msgid_tokens": [...], "msgstr_tokens": [...]}], "empty_msgstr": [keys], "parse_ok": bool}`.
- `msgid_mismatch` covers three kinds of damage: an ORIG key missing from NEW, an ORIG key whose msgid text changed, and a key present in NEW that ORIG never had (invented entry).
- Placeholder tokens = sorted multiset of `PLACEHOLDER_RE` matches, compared msgid vs msgstr for every entry with a non-empty msgstr. `entry_field` already DECODES `\n`/`\t`, so the regex must match the real newline/tab characters — not the two-character `\\n` sequence, which never appears in decoded text.
- Check runs over ALL non-obsolete entries of NEW (pre-existing translations included), msgid set compared against ORIG. Verified against real data: g10-veston-production (1006 translations), g10-production and g10-report all self-check clean, so scanning pre-existing entries produces no false blockers on this project.

- [ ] **Step 1: Write the failing tests**

Append to `~/.claude/skills/odoo-wlc/tests/test_po_ops.py`:

```python
def test_check_pass():
    _write_fixture()
    _write_filled([{"key": "Production Name", "msgstr": "Tên sản lượng"}])
    _run("apply", FIXTURE_FILE, "/tmp/test_filled.json", "-o", "/tmp/test_out.po")
    out = _run("check", FIXTURE_FILE, "/tmp/test_out.po", check=False)
    assert out.returncode == 0
    assert json.loads(out.stdout)["ok"] is True


def test_check_catches_placeholder_and_msgid_damage():
    bad = '''msgid "Report %s of %d items"
msgstr "Báo cáo %d của %d mục"

msgid "Batch <b>number</b>"
msgstr "Số lô"

msgid "Mutated"
msgstr "Đã sửa"
'''
    Path("/tmp/test_bad_new.po").write_text(bad, encoding="utf-8")
    orig = ('msgid "Report %s of %d items"\nmsgstr ""\n\n'
            'msgid "Batch <b>number</b>"\nmsgstr ""\n')
    Path("/tmp/test_bad_orig.po").write_text(orig, encoding="utf-8")
    out = _run("check", "/tmp/test_bad_orig.po", "/tmp/test_bad_new.po", check=False)
    report = json.loads(out.stdout)
    assert out.returncode == 1
    assert report["ok"] is False
    assert len(report["placeholder_mismatch"]) == 2   # %s/%d swap + missing <b></b>
    assert "Mutated" in report["msgid_mismatch"]      # key absent from ORIG


def test_check_catches_dropped_newline():
    Path("/tmp/test_nl_orig.po").write_text('msgid "Line one\\nLine two"\nmsgstr ""\n', encoding="utf-8")
    Path("/tmp/test_nl_new.po").write_text('msgid "Line one\\nLine two"\nmsgstr "Dòng một Dòng hai"\n',
                                           encoding="utf-8")
    out = _run("check", "/tmp/test_nl_orig.po", "/tmp/test_nl_new.po", check=False)
    assert out.returncode == 1
    assert json.loads(out.stdout)["placeholder_mismatch"][0]["msgid_tokens"] == ["\n"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 3 new FAIL.

- [ ] **Step 3: Implement cmd_check**

Insert above `main` in `~/.claude/skills/odoo-wlc/scripts/po_ops.py`:

```python
# Tokens are matched on DECODED strings, so \n and \t are the real characters.
PLACEHOLDER_RE = re.compile(r'%(?:\([^)]*\))?[sd]|%[sd]|%%|\n|\t|<[^>]+>')


def _ph_tokens(s):
    return sorted(PLACEHOLDER_RE.findall(s))


def _translated_map(path):
    text = open(path, encoding='utf-8').read()
    result = {}
    for e in _payload_entries(text):
        result[entry_key(e)] = (entry_field(e, 'msgid'), entry_field(e, 'msgstr') or '')
    return result


def cmd_check(orig_path, new_path):
    orig, new = _translated_map(orig_path), _translated_map(new_path)
    mismatch = [k for k in orig if k not in new or new[k][0] != orig[k][0]]
    mismatch += [k for k in new if k not in orig]
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

Rules encoded here: entries untranslated in ORIG that stay untranslated in NEW are fine; entries
translated in NEW must have matching placeholders; entries translated in ORIG that turn up empty
in NEW go to `empty_msgstr`; keys added or msgids altered go to `msgid_mismatch`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/test_po_ops.py -v
```

Expected: 15 passed.

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
  - `load_config(path='~/.weblate') -> {"url": str, "key": str}` — parsed with `ConfigParser(delimiters=('=',))`: option names under `[keys]` are URLs, and the default `':'` delimiter would split `https://host/api/` after `https`. The key whose option name matches `[weblate] url` wins (first non-empty as fallback). `WLC_URL`/`WLC_KEY` env take precedence and both must be set together.
  - `api_get(cfg, path) -> dict` — GET `{url}{path}` with `Authorization: Token {key}` **and a non-default `User-Agent`**; translate.vdx.vn answers HTTP 403 to `Python-urllib/3.x` (verified: identical request with `User-Agent: odoo-wlc/1.0` returns 200). Path starts without a leading slash (e.g. `projects/may10-odoo-qms/components/`).
  - `api_get_paged(cfg, path) -> list` — follows DRF `next` links and concatenates `results`.
  - `component_stats(cfg, project, slug, lang) -> dict` — Weblate's `/statistics/` payload has NO `untranslated` field (real keys: `total, translated, fuzzy, approved, readonly, failing, suggestions, …`), so untranslated is derived as `total - translated - fuzzy`, matching `po_ops.py stats` exactly. Language missing on the component (404) → all counts `None`.
  - `construct_mr_url(repo, source_branch, target_branch) -> str` — `https://gitlab.vdx.vn/may10/odoo-qms/-/merge_requests/new?merge_request%5Bsource_branch%5D=...&merge_request%5Btarget_branch%5D=...`; strips userinfo (`oauth2:...@`) and `.git` suffix from repo; URL-encodes branch names
  - CLI:
    - `weblate_api.py components PROJECT` → JSON list `[{"slug": ..., "name": ...}]`
    - `weblate_api.py stats PROJECT LANG` → JSON list `[{"slug": ..., "untranslated": int|null, "fuzzy": int|null, "total": int|null}]`, fanned out over a `ThreadPoolExecutor` (30 components: ~46 s sequential → ~3 s)
    - `weblate_api.py push-branch PROJECT COMPONENT` → `{"repo": ..., "branch": ..., "push_branch": ...}`
    - `weblate_api.py mr-url PROJECT COMPONENT` → constructed fallback URL (uses push-branch data)

- [ ] **Step 1: Write the failing tests**

Create `~/.claude/skills/odoo-wlc/tests/test_weblate_api.py`:

```python
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import weblate_api

INI = """[weblate]
url = https://translate.vdx.vn/api/

[keys]
https://other.example.com/api/ = OTHERKEY
https://translate.vdx.vn/api/ = SECRETKEY
"""


def _ini(tmp_path, monkeypatch):
    monkeypatch.delenv("WLC_URL", raising=False)
    monkeypatch.delenv("WLC_KEY", raising=False)
    ini = tmp_path / "weblate"
    ini.write_text(INI, encoding="utf-8")
    return str(ini)


def test_load_config_ini(tmp_path, monkeypatch):
    # option names are URLs: ConfigParser must not treat ':' as a delimiter
    cfg = weblate_api.load_config(_ini(tmp_path, monkeypatch))
    assert cfg == {"url": "https://translate.vdx.vn/api/", "key": "SECRETKEY"}


def test_load_config_picks_key_matching_url(tmp_path, monkeypatch):
    cfg = weblate_api.load_config(_ini(tmp_path, monkeypatch))
    assert cfg["key"] == "SECRETKEY"      # not OTHERKEY, which is listed first


def test_load_config_env_precedence(tmp_path, monkeypatch):
    path = _ini(tmp_path, monkeypatch)
    monkeypatch.setenv("WLC_URL", "https://env.example.com/api/")
    monkeypatch.setenv("WLC_KEY", "ENVKEY")
    assert weblate_api.load_config(path) == {"url": "https://env.example.com/api/", "key": "ENVKEY"}


def test_api_get_sends_token_and_user_agent(monkeypatch):
    seen = {}

    def fake_urlopen(req):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.headers)
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(weblate_api.urllib.request, "urlopen", fake_urlopen)
    cfg = {"url": "https://translate.vdx.vn/api/", "key": "K"}
    assert weblate_api.api_get(cfg, "projects/p/") == {"ok": True}
    assert seen["url"] == "https://translate.vdx.vn/api/projects/p/"
    # server answers 403 without a non-default User-Agent
    assert seen["headers"]["User-agent"] == weblate_api.USER_AGENT
    assert seen["headers"]["Authorization"] == "Token K"


def test_components_follow_pagination(monkeypatch):
    pages = {
        "projects/p/components/": {"results": [{"slug": "a", "name": "A"}],
                                   "next": "https://x/api/projects/p/components/?page=2"},
        "projects/p/components/?page=2": {"results": [{"slug": "b", "name": "B"}], "next": None},
    }
    monkeypatch.setattr(weblate_api, "api_get", lambda cfg, path: pages[path])
    cfg = {"url": "https://x/api/", "key": "K"}
    assert weblate_api.cmd_components(cfg, "p") == [{"slug": "a", "name": "A"},
                                                    {"slug": "b", "name": "B"}]


def test_component_stats_derives_untranslated(monkeypatch):
    # Weblate statistics has no `untranslated` field: total - translated - fuzzy
    monkeypatch.setattr(weblate_api, "api_get",
                        lambda cfg, path: {"total": 1015, "translated": 997, "fuzzy": 9})
    assert weblate_api.component_stats({}, "p", "c", "vi") == {
        "slug": "c", "untranslated": 9, "fuzzy": 9, "total": 1015}


def test_component_stats_missing_language(monkeypatch):
    def boom(cfg, path):
        raise SystemExit("404")

    monkeypatch.setattr(weblate_api, "api_get", boom)
    assert weblate_api.component_stats({}, "p", "c", "zz") == {
        "slug": "c", "untranslated": None, "fuzzy": None, "total": None}


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
from concurrent.futures import ThreadPoolExecutor

# translate.vdx.vn rejects the default Python-urllib agent with HTTP 403.
USER_AGENT = "odoo-wlc/1.0"


def load_config(path="~/.weblate"):
    url, key = os.environ.get("WLC_URL"), os.environ.get("WLC_KEY")
    if url and key:
        return {"url": url, "key": key}
    # delimiters=('=',) — option names are URLs; the default ':' delimiter
    # would split "https://host/api/" at "https".
    cp = configparser.ConfigParser(delimiters=('=',))
    if not cp.read(os.path.expanduser(path)):
        raise SystemExit("error: no ~/.weblate and no WLC_URL/WLC_KEY — run wlc setup first")
    url = cp.get("weblate", "url").strip().rstrip("/") + "/"
    keys = {opt.strip().rstrip("/") + "/": val.strip() for opt, val in cp.items("keys")}
    key = keys.get(url) or next((v for v in keys.values() if v), None)
    if not key:
        raise SystemExit("error: no API key for %s in %s" % (url, path))
    return {"url": url, "key": key}


def api_get(cfg, path):
    full = cfg["url"] + path.lstrip("/")
    req = urllib.request.Request(full, headers={"Authorization": "Token " + cfg["key"],
                                                "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("error: Weblate API %s returned %s" % (full, e.code))
    except urllib.error.URLError as e:
        raise SystemExit("error: Weblate API %s unreachable: %s" % (full, e.reason))


def api_get_paged(cfg, path):
    """Follow DRF pagination, returning the concatenated `results`."""
    out, page = [], api_get(cfg, path)
    while True:
        out.extend(page["results"])
        nxt = page.get("next")
        if not nxt:
            return out
        page = api_get(cfg, nxt[len(cfg["url"]):] if nxt.startswith(cfg["url"]) else nxt)


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
    return [{"slug": c["slug"], "name": c["name"]}
            for c in api_get_paged(cfg, "projects/%s/components/" % project)]


def component_stats(cfg, project, slug, lang):
    """Weblate statistics carry no `untranslated` field — derive it."""
    try:
        s = api_get(cfg, "translations/%s/%s/%s/statistics/" % (project, slug, lang))
    except SystemExit:                      # 404 = language not present on component
        return {"slug": slug, "untranslated": None, "fuzzy": None, "total": None}
    return {"slug": slug,
            "untranslated": s["total"] - s["translated"] - s["fuzzy"],
            "fuzzy": s["fuzzy"],
            "total": s["total"]}


def cmd_stats(cfg, project, lang):
    slugs = [c["slug"] for c in cmd_components(cfg, project)]
    with ThreadPoolExecutor(max_workers=8) as pool:      # ~30 components: 46s -> ~3s
        return list(pool.map(lambda s: component_stats(cfg, project, s, lang), slugs))


def push_branch_info(cfg, project, component):
    c = api_get(cfg, "components/%s/%s/" % (project, component))
    return {"repo": c["repo"], "branch": c["branch"],
            "push_branch": c.get("push_branch") or c["branch"]}


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

Expected: 8 passed.

- [ ] **Step 5: Live smoke against real server (read-only)**

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py push-branch may10-odoo-qms g10-access-management
# expect: {"repo": "https://gitlab.vdx.vn/may10/odoo-qms.git", "branch": "dev", "push_branch": "weblate-translations"}
time python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py stats may10-odoo-qms vi | head -c 400
# expect: 30 rows in ~3s; components without a vi translation report null counts (16 of 30 today)
python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py mr-url may10-odoo-qms g10-access-management
# expect URL starting https://gitlab.vdx.vn/may10/odoo-qms/-/merge_requests/new?merge_request%5Bsource_branch%5D=weblate-translations
```

A 403 from any call means the `User-Agent` header was dropped — that is the server's WAF, not a bad token. A garbled key (`//translate.vdx.vn/api/ = …`) means the `delimiters=('=',)` argument was dropped.

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
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py stats "$WORK/<lang>.orig.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py dump "$WORK/<lang>.orig.po" > "$WORK/pending.json"
```

Local `untranslated` must equal the API number from step 1. A mismatch means the component
changed since the report — re-run step 1 for that component before continuing.

### 3. Translate (Claude does the translation)

For every entry in `pending.json`:
- Glossary lookup: `grep -P -i "^\d+\t<msgid-escaped>\t" ~/.claude/skills/odoo-wlc/reference/glossary.tsv`
  (escape `|()\.` for grep -P; msgid is column 2). Hit → use column 3 msgstr.
  Caveat: ~58 of 2262 glossary rows hold multi-line msgids and are split across lines, so a
  line-anchored grep silently misses them. Multi-line or no-hit terms → translate yourself.
- Miss → translate yourself: Odoo/QMS domain Vietnamese, keep placeholders EXACT
  (`%s`, `%d`, `%(...)s`, `%%`, newlines, tabs, XML tags), title-case like Odoo UI conventions.
- Location comments (`model:ir.model.fields,...` = field label, `arch_db` = view text,
  `code:` = runtime string) inform register/length.
- Ambiguous or business-critical terms → translate + flag in the review summary.
  Genuinely unsure → emit `"msgstr": ""` for that key: `apply` leaves the entry untranslated
  instead of guessing, and it is not reported as an unknown key.
Write `{"entries": [{"key": ..., "msgstr": ...}]}` to `$WORK/filled.json` (all entries, one file per component).

### 4. Build + validate

```bash
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py apply "$WORK/<lang>.orig.po" "$WORK/filled.json" -o "$WORK/<lang>.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py check "$WORK/<lang>.orig.po" "$WORK/<lang>.po"
```

`apply` reporting a non-empty `skipped_unknown_keys` means a key was invented or the file moved
on — re-run `dump` and rebuild `filled.json` for those keys.
`check` exit 1 → fix reported entries (placeholder and msgid mismatches are blockers), rerun.
Never upload with failing check.

### 5. Review gate (single, all components)

Present:
- Table: component | translated | deferred (empty msgstr) | warnings | glossary misses (term → proposed)
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

- `wlc upload` fails "locked" → `"$WLC" unlock <project>/<component>` (unlock is a
  component-level operation — do not pass the `/lang` suffix), retry once.
- `wlc push` fails (non-fast-forward / upstream moved) → `"$WLC" pull <project>`, then re-run
  step 2 (re-download, re-apply via `apply` against fresh orig — msgstrs from filled.json are reused),
  re-check, re-upload only if diffs changed, then `commit` + `push` again.
- Any Weblate API `Object not found` → wrong slug; list with
  `python3 ~/.claude/skills/odoo-wlc/scripts/weblate_api.py components <project>`.
- Weblate API HTTP 403 → the request lost its `User-Agent` header (server WAF rejects
  `Python-urllib/*`), not an auth problem. HTTP 401 → bad/expired token in `~/.weblate`.

## Rules (from reference/translation-flow.md)

- Never edit `.po`/`.pot` in the source repo. Changes go: upload → Weblate commit → push → MR.
- msgid text is never modified by us; `check` enforces it.
- Fuzzy entries are out of scope; obsolete (`#~`) entries are copied through untouched.
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

Pick one component with `untranslated > 0`. As of 2026-08-18 exactly three qualify:
`g10-veston-production` (9 untranslated, 9 fuzzy, 1015 total), `g10-report` (4/2/108),
`g10-production` (2/0/337). If all read 0, someone finished the language — pick another lang
or skip to Step 4.

- [ ] **Step 2: Dry-run the pipeline (download → dump → apply with 1 real translation → check)**

```bash
WORK=/tmp/odoo-wlc/may10-odoo-qms/<component>; mkdir -p "$WORK"
"$WLC" download may10-odoo-qms/<component>/vi --output "$WORK/vi.orig.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py stats "$WORK/vi.orig.po"
# local untranslated/fuzzy/total must equal the API row from Step 1
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py dump "$WORK/vi.orig.po" > "$WORK/pending.json"
# translate just ONE entry into filled.json by hand for the test
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py apply "$WORK/vi.orig.po" "$WORK/filled.json" -o "$WORK/vi.po"
python3 ~/.claude/skills/odoo-wlc/scripts/po_ops.py check "$WORK/vi.orig.po" "$WORK/vi.po"; echo "exit=$?"
diff <(grep -c '' "$WORK/vi.orig.po") <(grep -c '' "$WORK/vi.po") && echo SAME_LINE_COUNT
```

Expected: check exit 0; `diff vi.orig.po vi.po` shows exactly two changed lines (one msgstr
swapped); identical line count; header block (msgid "") byte-identical.

- [ ] **Step 3: STOP — do not upload/push in this task.** Report results. Real upload happens on first user-invoked run.

- [ ] **Step 4: Full test suite + permissions**

```bash
cd ~/.claude/skills/odoo-wlc && python3 -m pytest tests/ -v    # expect 23 passed (15 po_ops + 8 weblate_api)
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

**Verification pass (2026-08-18, all plan code executed before writing it here):**
- Every code block in Tasks 2-6 was run; the suite is green at 23 tests (15 `po_ops` + 8 `weblate_api`).
- The whole pipeline ran against real data: downloaded `g10-veston-production/vi` (1015 entries),
  dumped 9 untranslated, applied 9, output kept the same 7348 lines with exactly 18 diff lines
  (9 × msgstr), `check` exit 0, `stats` then reported 0 untranslated.
- `weblate_api.py` was smoke-tested live read-only: `push-branch` returns the documented repo/branch/
  push_branch, `mr-url` matches the expected fallback URL, `stats` returns 30 rows in ~3 s and its
  untranslated numbers equal the local `po_ops` numbers on all three pending components.
- Fixed before landing: HTTP 403 on default urllib User-Agent; `ConfigParser` `':'` delimiter
  shredding the `[keys]` URL; missing `untranslated` field in Weblate statistics; fixture/expectation
  mismatches in four tests; `skipped_unknown_keys` swallowing deferred entries; stray trailing blank
  line from `apply`; dead `\\n`/`\\t` branches in the placeholder regex; first-key-wins auth
  selection; unpaginated component listing; 46 s sequential stats; component-level `wlc unlock`;
  fuzzy accounting; glossary multi-line rows.
- Still unverified by design: `wlc push` output containing the MR URL (needs a real mutation);
  the constructed `merge_requests/new?...` URL is the fallback for exactly that case.

**Placeholder scan:** no TBD/TODO, no deliberately-wrong code samples — every block in this plan is
the block that was executed. **Type consistency:** `entry_key`/`po_quote`/`po_unquote`/`is_obsolete`/
`is_fuzzy`/`_payload_entries` names consistent across Tasks 2-5; filled.json shape
`{"entries":[{"key","msgstr"}]}` identical in Task 3 (dump emits extra fields — apply reads only
key/msgstr) and SKILL.md §3; `stats` output shape (`total`/`untranslated`/`fuzzy`) identical between
`po_ops.py`, `weblate_api.py`, and the SKILL.md report table.
