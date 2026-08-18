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
