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


def _bare(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
    return path


def _clone(bare: Path, into: Path, name: str = "origin") -> Path:
    subprocess.run(["git", "clone", "-q", str(bare), str(into)], check=True)
    subprocess.run(["git", "-C", str(into), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(into), "config", "user.name", "T"], check=True)
    return into


def _commit(repo: Path, filename: str, subject: str) -> None:
    (repo / filename).write_text(subject, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", subject], check=True)


def test_current_branch(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:main"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    assert gitlab_ci.current_branch(str(repo)) == "feature-x"


def test_has_tracked_changes_ignores_untracked(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    (repo / "untracked.txt").write_text("x", encoding="utf-8")
    assert gitlab_ci.has_tracked_changes(str(repo)) is False


def test_has_tracked_changes_true_for_staged_and_unstaged(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    assert gitlab_ci.has_tracked_changes(str(repo)) is True


def test_rebase_onto_success(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(repo, "b.txt", "feature work")
    other = _clone(bare, tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "dev"], check=True)
    _commit(other, "c.txt", "upstream work")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "upstream", str(bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "upstream", "dev"], check=True)

    assert gitlab_ci.rebase_onto(str(repo), "upstream/dev") is None
    assert (repo / "c.txt").is_file()  # upstream commit now in history


def test_rebase_onto_conflict_aborts_and_lists_files(tmp_path):
    bare = _bare(tmp_path / "bare.git")
    repo = _clone(bare, tmp_path / "repo")
    _commit(repo, "a.txt", "init")
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(repo, "a.txt", "feature change")
    other = _clone(bare, tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "dev"], check=True)
    _commit(other, "a.txt", "conflicting upstream change")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "dev"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "upstream", str(bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "upstream", "dev"], check=True)

    conflicts = gitlab_ci.rebase_onto(str(repo), "upstream/dev")
    assert conflicts == ["a.txt"]
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                             capture_output=True, text=True).stdout
    assert status.strip() == ""  # rebase was aborted, tree is clean again


def _push_setup(tmp_path, monkeypatch):
    """Fork (origin) + upstream bare repos, a working clone tracking origin,
    upstream added as a second remote, on branch feature-x with one commit
    ahead of upstream/dev. Returns (repo, upstream_bare)."""
    upstream_bare = _bare(tmp_path / "upstream.git")
    seed = _clone(upstream_bare, tmp_path / "seed")
    _commit(seed, "a.txt", "init")
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:dev"], check=True)

    fork_bare = _bare(tmp_path / "fork.git")
    subprocess.run(["git", "clone", "-q", "--bare", str(upstream_bare), str(fork_bare)],
                    check=False)  # fork starts equal to upstream; ignore if already bare-cloned

    repo = _clone(upstream_bare, tmp_path / "repo", name="upstream")
    subprocess.run(["git", "-C", str(repo), "remote", "rename", "origin", "upstream"],
                    check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(fork_bare)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature-x", "upstream/dev"], check=True)
    _commit(repo, "b.txt", "feature work")

    monkeypatch.chdir(repo)
    cfg_dir = repo / "config"
    cfg_dir.mkdir()
    (cfg_dir / "project.json").write_text(
        json.dumps({"git_root": str(repo), "gitlab_url": "https://gitlab.vdx.vn"}), encoding="utf-8")
    return repo, upstream_bare


def _stub_mr_api(monkeypatch, existing=None, created=None):
    calls = []

    def fake_api_request(token, method, url, data=None, **kw):
        calls.append((method, url, data))
        if method == "GET":
            return existing or []
        return created or {"iid": 1, "web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/1"}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id",
                         lambda token, gitlab_url, path: {"sungroup/sca": 21, "truong/sca": 90}[path])
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path",
                         lambda remote, root: {"upstream": "sungroup/sca", "origin": "truong/sca"}[remote])
    return calls


def test_cmd_push_refuses_dirty_tree(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    (repo / "b.txt").write_text("dirty", encoding="utf-8")
    try:
        gitlab_ci.cmd_push(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "tracked" in str(e.code) or "dirty" in str(e.code)


def test_cmd_push_refuses_protected_branch(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "dev"], check=True)
    try:
        gitlab_ci.cmd_push(target="dev")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_cmd_push_creates_mr_with_default_title(tmp_path, monkeypatch):
    repo, upstream_bare = _push_setup(tmp_path, monkeypatch)
    calls = _stub_mr_api(monkeypatch, existing=[], created={
        "iid": 7, "web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/7"})

    result = gitlab_ci.cmd_push(target="dev")

    assert result["mr_url"] == "https://gitlab.vdx.vn/g/p/-/merge_requests/7"
    assert result["mr_iid"] == 7
    assert result["pushed"] is True
    assert "since" in result
    post_calls = [c for c in calls if c[0] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0][2]["title"] == "feature work"
    assert post_calls[0][2]["description"] == "- feature work"
    assert post_calls[0][2]["target_project_id"] == 21
    assert "merge_when_pipeline_succeeds" not in post_calls[0][2]


def test_cmd_push_reuses_open_mr(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    calls = _stub_mr_api(monkeypatch, existing=[
        {"iid": 3, "web_url": "https://gitlab.vdx.vn/g/p/-/merge_requests/3",
         "source_project_id": 90}])

    result = gitlab_ci.cmd_push(target="dev")

    assert result["mr_iid"] == 3
    assert not [c for c in calls if c[0] == "POST"]  # never created a second MR


def test_cmd_push_no_push_when_origin_already_at_head(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "HEAD:feature-x"], check=True)
    _stub_mr_api(monkeypatch, existing=[{"iid": 3, "web_url": "https://x/3", "source_project_id": 90}])

    result = gitlab_ci.cmd_push(target="dev")

    assert result["pushed"] is False
    assert "since" not in result


def test_cmd_push_rebase_conflict_exits_4(tmp_path, monkeypatch):
    repo, upstream_bare = _push_setup(tmp_path, monkeypatch)
    other = _clone(upstream_bare, tmp_path / "other")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "dev"], check=True)
    (other / "b.txt").write_text("conflicting upstream change", encoding="utf-8")
    subprocess.run(["git", "-C", str(other), "add", "b.txt"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-q", "-m", "upstream b.txt"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "dev"], check=True)

    try:
        gitlab_ci.cmd_push(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 4


def test_cmd_push_no_rebase_fast_forward_push(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    _stub_mr_api(monkeypatch, existing=[{"iid": 3, "web_url": "https://x/3", "source_project_id": 90}])

    result = gitlab_ci.cmd_push(target="dev", no_rebase=True)

    assert result["pushed"] is True
    fork_head = subprocess.run(["git", "-C", str(repo), "ls-remote", "origin", "feature-x"],
                                capture_output=True, text=True).stdout
    local_head = gitlab_ci.rev_parse(str(repo), "HEAD")
    assert local_head in fork_head


def test_cmd_push_non_fast_forward_exits_5(tmp_path, monkeypatch):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    fork_bare = Path(subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True).stdout.strip())
    other = _clone(fork_bare, tmp_path / "other-fork-clone")
    subprocess.run(["git", "-C", str(other), "checkout", "-q", "-b", "feature-x"], check=True)
    _commit(other, "z.txt", "someone else pushed to the fork branch")
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "feature-x"], check=True)

    try:
        gitlab_ci.cmd_push(target="dev", no_rebase=True)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 5


def test_main_push_prints_one_json_line_and_exits_0(tmp_path, monkeypatch, capsys):
    repo, _ = _push_setup(tmp_path, monkeypatch)
    _stub_mr_api(monkeypatch, existing=[{"iid": 3, "web_url": "https://x/3", "source_project_id": 90}])

    code = gitlab_ci.main(["push", "--target", "dev"])

    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["mr_iid"] == 3


def test_main_wraps_message_only_systemexit_as_10(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_push", lambda **kw: (_ for _ in ()).throw(
        SystemExit("error: boom")))
    code = gitlab_ci.main(["push"])
    assert code == 10


def test_main_passes_through_int_systemexit(monkeypatch):
    monkeypatch.setattr(gitlab_ci, "cmd_push", lambda **kw: (_ for _ in ()).throw(SystemExit(4)))
    assert gitlab_ci.main(["push"]) == 4
