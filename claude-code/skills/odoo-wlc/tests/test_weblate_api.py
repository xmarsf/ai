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


def test_parse_repo_strips_credentials_and_git():
    host, proj = weblate_api.parse_repo(
        "https://oauth2:token123@gitlab.vdx.vn/may10/odoo-qms.git")
    assert (host, proj) == ("gitlab.vdx.vn", "may10/odoo-qms")


GITLAB_INI = """[gitlab]
https://gitlab.vdx.vn/ = GLTOKEN
"""


def _gitlab_ini(tmp_path):
    ini = tmp_path / "gitlab"
    ini.write_text(GITLAB_INI, encoding="utf-8")
    return str(ini)


def test_load_gitlab_config_matches_by_host(tmp_path):
    tokens = weblate_api.load_gitlab_config(_gitlab_ini(tmp_path))
    assert weblate_api.gitlab_token_for_host(tokens, "gitlab.vdx.vn") == "GLTOKEN"


def test_gitlab_token_for_host_missing_raises(tmp_path):
    tokens = weblate_api.load_gitlab_config(_gitlab_ini(tmp_path))
    try:
        weblate_api.gitlab_token_for_host(tokens, "other.example.com")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_find_mr_sends_private_token_and_state_opened(monkeypatch):
    seen = {}

    def fake_urlopen(req):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.headers)
        return io.BytesIO(json.dumps(
            [{"web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/7",
              "updated_at": "2026-08-20T10:00:00Z"}]).encode("utf-8"))

    monkeypatch.setattr(weblate_api.urllib.request, "urlopen", fake_urlopen)
    url = weblate_api.find_mr("gitlab.vdx.vn", "g/p", "GLTOKEN", "weblate-translations", "dev")
    assert url == "https://gitlab.vdx.vn/g/p/-/merge_requests/7"
    assert seen["headers"]["Private-token"] == "GLTOKEN"
    assert "state=opened" in seen["url"]
    assert "source_branch=weblate-translations" in seen["url"]
    assert "target_branch=dev" in seen["url"]


def test_find_mr_picks_most_recently_updated(monkeypatch):
    def fake_urlopen(req):
        return io.BytesIO(json.dumps([
            {"web_url": "https://x/mr/1", "updated_at": "2026-08-19T10:00:00Z"},
            {"web_url": "https://x/mr/2", "updated_at": "2026-08-20T10:00:00Z"},
        ]).encode("utf-8"))

    monkeypatch.setattr(weblate_api.urllib.request, "urlopen", fake_urlopen)
    url = weblate_api.find_mr("gitlab.vdx.vn", "g/p", "GLTOKEN", "src", "dev")
    assert url == "https://x/mr/2"


def test_find_mr_no_open_mr_raises(monkeypatch):
    monkeypatch.setattr(weblate_api.urllib.request, "urlopen",
                        lambda req: io.BytesIO(b"[]"))
    try:
        weblate_api.find_mr("gitlab.vdx.vn", "g/p", "GLTOKEN", "src", "dev")
        assert False, "expected SystemExit"
    except SystemExit:
        pass
