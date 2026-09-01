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
