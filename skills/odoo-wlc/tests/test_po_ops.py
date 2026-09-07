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
