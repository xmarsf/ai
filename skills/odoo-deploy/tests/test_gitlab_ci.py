import io
import json
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gitlab_ci


def _write_project_config(root: Path, **fields) -> Path:
    base = {"git_root": str(root / "repo"), "gitlab_url": "https://gitlab.vdx.vn"}
    base.update(fields)
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "project.json").write_text(json.dumps(base), encoding="utf-8")
    return cfg_dir / "project.json"


def test_load_project_config_walks_up(tmp_path, monkeypatch):
    _write_project_config(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    cfg = gitlab_ci.load_project_config()
    assert cfg["git_root"] == str(tmp_path / "repo")
    assert cfg["gitlab_url"] == "https://gitlab.vdx.vn"


def test_load_project_config_missing_file_exits_10(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    try:
        gitlab_ci.load_project_config()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code != 0


def test_load_project_config_missing_required_key_exits(tmp_path, monkeypatch):
    _write_project_config(tmp_path, gitlab_url="")
    monkeypatch.chdir(tmp_path)
    try:
        gitlab_ci.load_project_config()
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_parse_remote_url_https():
    assert gitlab_ci.parse_remote_url("https://gitlab.vdx.vn/sungroup/sca") == \
        ("gitlab.vdx.vn", "sungroup/sca")


def test_parse_remote_url_https_with_git_suffix():
    assert gitlab_ci.parse_remote_url("https://gitlab.vdx.vn/truong/sca.git") == \
        ("gitlab.vdx.vn", "truong/sca")


def test_parse_remote_url_ssh_scp_form():
    assert gitlab_ci.parse_remote_url("git@gitlab.vdx.vn:sungroup/sca.git") == \
        ("gitlab.vdx.vn", "sungroup/sca")


def test_parse_remote_url_ssh_url_form():
    assert gitlab_ci.parse_remote_url("ssh://git@gitlab.vdx.vn/sungroup/sca.git") == \
        ("gitlab.vdx.vn", "sungroup/sca")


def test_git_remote_project_path_reads_git_remote(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(args, 0, stdout="https://gitlab.vdx.vn/sungroup/sca\n", stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    assert gitlab_ci.git_remote_project_path("upstream", "/repo") == "sungroup/sca"
    assert seen["args"] == ["git", "remote", "get-url", "upstream"]
    assert seen["cwd"] == "/repo"


def test_git_remote_project_path_none_when_remote_missing(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="error: No such remote")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    assert gitlab_ci.git_remote_project_path("upstream", "/repo") is None


GITLAB_INI = "[gitlab]\nhttps://gitlab.vdx.vn/ = FILETOKEN\n"


def test_resolve_gitlab_token_from_file(tmp_path, monkeypatch):
    ini = tmp_path / "gitlab"
    ini.write_text(GITLAB_INI, encoding="utf-8")
    monkeypatch.setattr(gitlab_ci, "GITLAB_TOKEN_FILE", str(ini))
    assert gitlab_ci.resolve_gitlab_token("gitlab.vdx.vn") == "FILETOKEN"


def test_resolve_gitlab_token_falls_back_to_git_credential(tmp_path, monkeypatch):
    ini = tmp_path / "nope"
    monkeypatch.setattr(gitlab_ci, "GITLAB_TOKEN_FILE", str(ini))

    def fake_run(args, **kwargs):
        assert args == ["git", "credential", "fill"]
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["input"] == "protocol=https\nhost=gitlab.vdx.vn\n\n"
        return subprocess.CompletedProcess(args, 0, stdout="password=CREDTOKEN\n", stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    assert gitlab_ci.resolve_gitlab_token("gitlab.vdx.vn") == "CREDTOKEN"


def test_resolve_gitlab_token_neither_exits_10(tmp_path, monkeypatch):
    monkeypatch.setattr(gitlab_ci, "GITLAB_TOKEN_FILE", str(tmp_path / "nope"))

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    try:
        gitlab_ci.resolve_gitlab_token("gitlab.vdx.vn")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "no GitLab token" in str(e.code)


def _http_error(url, code, body=b"{}"):
    return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(body))


def test_api_request_get_success(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert req.headers["User-agent"] == gitlab_ci.USER_AGENT
        assert req.headers["Authorization"] == "Bearer TOK"
        return io.BytesIO(b'{"id": 1}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    assert gitlab_ci.api_request("TOK", "GET", "https://x/api/v4/y") == {"id": 1}


def test_api_request_retries_connection_error_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("dns failure")
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: sleeps.append(s))
    assert gitlab_ci.api_request("TOK", "GET", "https://x/y") == {"ok": True}
    assert calls["n"] == 3
    assert sleeps == [2, 5]


def test_api_request_retries_5xx_and_429_for_get(monkeypatch):
    codes = iter([503, 429])
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        try:
            code = next(codes)
        except StopIteration:
            return io.BytesIO(b'{"ok": true}')
        raise _http_error(req.full_url, code)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    assert gitlab_ci.api_request("TOK", "GET", "https://x/y") == {"ok": True}
    assert calls["n"] == 3


def test_api_request_other_4xx_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(req.full_url, 404)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    try:
        gitlab_ci.api_request("TOK", "GET", "https://x/y")
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert calls["n"] == 1


def test_api_request_post_not_retried_after_http_response(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(req.full_url, 500)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    try:
        gitlab_ci.api_request("TOK", "POST", "https://x/y", data={"a": 1})
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert calls["n"] == 1  # a 500 IS a response — never retried for POST


def test_api_request_post_retried_on_connection_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("connection refused")
        return io.BytesIO(b'{"id": 5}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    assert gitlab_ci.api_request("TOK", "POST", "https://x/y", data={"a": 1}) == {"id": 5}
    assert calls["n"] == 2
