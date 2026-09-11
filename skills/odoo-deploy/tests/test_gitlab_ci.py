import io
import json
import subprocess
import sys
import time
import urllib.error
import zipfile
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


def test_git_remote_project_path_exits_when_remote_missing(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="error: No such remote")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    try:
        gitlab_ci.git_remote_project_path("upstream", "/repo")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "no 'upstream' git remote" in str(e.code)


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


def test_main_wraps_unexpected_exception_as_10(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_wait", lambda **kw: (_ for _ in ()).throw(
        ValueError("boom")))
    code = gitlab_ci.main(["wait", "--mr", "7", "--sha", "abc"])
    assert code == 10  # a crash is a tooling error, never 1 ("pipeline failed")
    assert "ValueError: boom" in capsys.readouterr().err


def _wait_env(monkeypatch, gets):
    """`gets` maps exact URL -> response dict; api_request(GET, url) looks it
    up. Any POST/other method is an error — wait never writes."""
    def fake_api_request(token, method, url, data=None, **kw):
        assert method == "GET"
        return gets[url]

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})


def _write_event(events_root, project_id, pipeline_id, received_ns, iid, sha, status):
    d = events_root / str(project_id) / str(pipeline_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{received_ns}.json").write_text(json.dumps({
        "object_kind": "pipeline",
        "object_attributes": {"id": pipeline_id, "sha": sha, "status": status},
        "merge_request": {"iid": iid, "source_project_id": 90},
        "project": {"id": project_id},
    }), encoding="utf-8")


def test_cmd_wait_initial_get_counting_status(monkeypatch):
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {
        "head_pipeline": {"id": 55, "project_id": 21, "sha": "abc",
                           "status": "success", "web_url": "https://x/p/55",
                           "finished_at": "2026-09-11T10:00:00.000Z"}}})

    result = gitlab_ci.cmd_wait(mr_iid=7, sha="abc")
    assert result == {"pipeline_id": 55, "project_id": 21,
                       "status": "success", "web_url": "https://x/p/55"}


def test_cmd_wait_since_rejects_stale_final_status(monkeypatch):
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    since = 2_000_000_000_000_000_000  # far in the future
    _wait_env(monkeypatch, {mr_url: {
        "head_pipeline": {"id": 55, "project_id": 21, "sha": "abc",
                           "status": "success", "web_url": "https://x/p/55",
                           "finished_at": "2026-09-11T10:00:00.000Z"}}})

    calls = {"sleep": 0}

    def sleep_and_stop(_s):
        calls["sleep"] += 1
        raise SystemExit(3)  # abort the loop after one pass, like a real timeout would

    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc", since=since, sleep_fn=sleep_and_stop, now_fn=lambda: 0)
    except SystemExit:
        pass
    # since is stale relative to finished_at -> falls through to event scanning,
    # which sleeps once before this test's injected sleep_fn aborts the loop
    assert calls["sleep"] == 1


def test_cmd_wait_scans_events_dir_for_final_status(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    pipeline_url = "https://gitlab.vdx.vn/api/v4/projects/21/pipelines/55"
    _wait_env(monkeypatch, {
        mr_url: {"head_pipeline": {"id": 55, "project_id": 21, "sha": "old",
                                    "status": "success", "finished_at": None}},
        pipeline_url: {"id": 55, "status": "failed", "web_url": "https://x/p/55",
                        "finished_at": "2026-09-11T10:00:00.000Z"},
    })
    _write_event(tmp_path, project_id=21, pipeline_id=55, received_ns=100,
                 iid=7, sha="abc", status="failed")

    result = gitlab_ci.cmd_wait(mr_iid=7, sha="abc", sleep_fn=lambda s: None,
                                 now_fn=lambda: 0)
    assert result == {"pipeline_id": 55, "project_id": 21,
                       "status": "failed", "web_url": "https://x/p/55"}


def test_cmd_wait_ignores_events_for_other_iid_sha_or_before_since(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {"head_pipeline": {"sha": "old", "status": "success"}}})
    _write_event(tmp_path, 21, 1, received_ns=50, iid=99, sha="abc", status="success")   # wrong iid
    _write_event(tmp_path, 21, 2, received_ns=50, iid=7, sha="zzz", status="success")    # wrong sha
    _write_event(tmp_path, 21, 3, received_ns=5, iid=7, sha="abc", status="success")     # before since

    calls = {"n": 0}

    def sleep_and_stop(_s):
        calls["n"] += 1
        raise SystemExit(3)  # abort the test after one scan pass, like a timeout would

    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc", since=10, sleep_fn=sleep_and_stop, now_fn=lambda: 0)
    except SystemExit:
        pass
    assert calls["n"] == 1  # none of the three events matched -> kept scanning


def test_cmd_wait_no_pipeline_after_10_minutes_exits_3(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {"head_pipeline": {"sha": "old", "status": "success"}}})

    clock = {"t": 0.0}
    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc",
                            sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s),
                            now_fn=lambda: clock["t"])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "no_pipeline"


def test_cmd_wait_timeout_flag_exits_3(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    mr_url = "https://gitlab.vdx.vn/api/v4/projects/21/merge_requests/7"
    _wait_env(monkeypatch, {mr_url: {"head_pipeline": {"sha": "abc", "status": "running"}}})

    clock = {"t": 0.0}
    try:
        gitlab_ci.cmd_wait(mr_iid=7, sha="abc", timeout_minutes=1,
                            sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s),
                            now_fn=lambda: clock["t"])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 3
    assert json.loads(capsys.readouterr().out)["reason"] == "timeout"


def test_main_wait_success_exits_0(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_wait", lambda **kw: {
        "pipeline_id": 55, "project_id": 21, "status": "success", "web_url": "https://x/p/55"
    })
    code = gitlab_ci.main(["wait", "--mr", "7", "--sha", "abc"])
    assert code == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["status"] == "success"


def test_main_wait_failed_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_wait", lambda **kw: {
        "pipeline_id": 55, "project_id": 21, "status": "failed", "web_url": "https://x/p/55"
    })
    code = gitlab_ci.main(["wait", "--mr", "7", "--sha", "abc"])
    assert code == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["status"] == "failed"


def test_main_wait_canceled_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_wait", lambda **kw: {
        "pipeline_id": 55, "project_id": 21, "status": "canceled", "web_url": "https://x/p/55"
    })
    code = gitlab_ci.main(["wait", "--mr", "7", "--sha", "abc"])
    assert code == 2
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["status"] == "canceled"


def test_main_wait_skipped_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(gitlab_ci, "cmd_wait", lambda **kw: {
        "pipeline_id": 55, "project_id": 21, "status": "skipped", "web_url": "https://x/p/55"
    })
    code = gitlab_ci.main(["wait", "--mr", "7", "--sha", "abc"])
    assert code == 2
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["status"] == "skipped"


def _fetch_logs_env(monkeypatch, jobs, raw=None):
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, data=None, **kw: jobs)
    monkeypatch.setattr(gitlab_ci, "api_request_raw", raw or (lambda token, url: b"trace\n"))
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})


def test_api_request_raw_sends_auth_and_user_agent(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert req.headers["Authorization"] == "Bearer TOK"
        assert req.headers["User-agent"] == gitlab_ci.USER_AGENT
        return io.BytesIO(b"raw-bytes")

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    assert gitlab_ci.api_request_raw("TOK", "https://x/y") == b"raw-bytes"


def test_api_request_raw_retries_connection_error_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("dns failure")
        return io.BytesIO(b"raw-data")

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: sleeps.append(s))
    assert gitlab_ci.api_request_raw("TOK", "https://x/y") == b"raw-data"
    assert calls["n"] == 3
    assert sleeps == [2, 5]


def test_api_request_raw_retries_5xx_and_429(monkeypatch):
    codes = iter([503, 429])
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        try:
            code = next(codes)
        except StopIteration:
            return io.BytesIO(b"success")
        raise _http_error(req.full_url, code)

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    assert gitlab_ci.api_request_raw("TOK", "https://x/y") == b"success"
    assert calls["n"] == 3


def test_api_request_raw_gives_up_after_retries_exhausted(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError("persistent failure")

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci.time, "sleep", lambda s: None)
    try:
        gitlab_ci.api_request_raw("TOK", "https://x/y")
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert calls["n"] == 3


def test_clean_trace_strips_ansi_and_timestamp_prefix():
    raw = (b"2026-09-11T10:00:00.123456Z 00O \x1b[32mok\x1b[0m\n"
           b"2026-09-11T10:00:01.000000Z 00O+ next line\n")
    assert gitlab_ci._clean_trace(raw) == "ok\nnext line\n"


def test_cmd_fetch_logs_skips_allow_failure_and_non_failed(monkeypatch, tmp_path):
    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "ruff", "stage": "quality", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure", "artifacts": []},
        {"id": 2, "name": "security-scan", "stage": "test", "status": "failed",
         "allow_failure": True, "failure_reason": "script_failure", "artifacts": []},
        {"id": 3, "name": "pytest", "stage": "test", "status": "success",
         "allow_failure": False, "failure_reason": None, "artifacts": []},
    ])

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))

    assert [j["job"] for j in result["jobs"]] == ["ruff"]
    assert (tmp_path / "ruff.log").read_text(encoding="utf-8") == "trace\n"


def test_cmd_fetch_logs_unzips_archive_artifact(monkeypatch, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("parallel-odoo-test.log", "FAILED some::test\n")
    zip_bytes = buf.getvalue()

    def fake_raw(token, url):
        return zip_bytes if url.endswith("/artifacts") else b"trace\n"

    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "parallel-odoo-pytest", "stage": "test", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure",
         "artifacts": [{"file_type": "archive", "filename": "artifacts.zip"}]},
    ], raw=fake_raw)

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))

    assert result["jobs"][0]["artifacts"] == str(tmp_path / "parallel-odoo-pytest")
    assert (tmp_path / "parallel-odoo-pytest" / "parallel-odoo-test.log").read_text(
        encoding="utf-8") == "FAILED some::test\n"


def test_cmd_fetch_logs_no_archive_artifacts_is_null(monkeypatch, tmp_path):
    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "ruff", "stage": "quality", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure", "artifacts": []},
    ])

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))
    assert result["jobs"][0]["artifacts"] is None


def test_cmd_fetch_logs_sanitizes_job_name_with_slash(monkeypatch, tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("report.log", "FAILED some::test\n")
    zip_bytes = buf.getvalue()

    def fake_raw(token, url):
        return zip_bytes if url.endswith("/artifacts") else b"trace\n"

    _fetch_logs_env(monkeypatch, jobs=[
        {"id": 1, "name": "parallel-odoo-pytest 1/3", "stage": "test", "status": "failed",
         "allow_failure": False, "failure_reason": "script_failure",
         "artifacts": [{"file_type": "archive", "filename": "artifacts.zip"}]},
    ], raw=fake_raw)

    result = gitlab_ci.cmd_fetch_logs(project_id=21, pipeline_id=55, out_dir=str(tmp_path))

    # The filesystem gets a sanitized name; the manifest keeps GitLab's real one.
    assert result["jobs"][0]["job"] == "parallel-odoo-pytest 1/3"
    assert result["jobs"][0]["trace"] == str(tmp_path / "parallel-odoo-pytest_1_3.log")
    assert (tmp_path / "parallel-odoo-pytest_1_3.log").read_text(encoding="utf-8") == "trace\n"
    assert result["jobs"][0]["artifacts"] == str(tmp_path / "parallel-odoo-pytest_1_3")
    assert (tmp_path / "parallel-odoo-pytest_1_3" / "report.log").is_file()


def test_safe_extract_rejects_zip_slip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")

    try:
        gitlab_ci._safe_extract(buf.getvalue(), tmp_path / "job-name")
        assert False, "expected SystemExit"
    except SystemExit:
        pass
    assert not (tmp_path.parent / "evil.txt").exists()


def test_parse_ci_config_path():
    assert gitlab_ci.parse_ci_config_path(
        "pipelines/sun-sca.yml@infra/cicd-pipeline-template:sca") == \
        ("pipelines/sun-sca.yml", "infra/cicd-pipeline-template", "sca")


def test_parse_ci_config_path_malformed_exits():
    try:
        gitlab_ci.parse_ci_config_path("not-a-valid-path")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_yaml_scalar_extracts_quoted_value():
    text = 'variables:\n  ENABLE_RUFF: "true"\n  IGNORE_LINTERS: "mod_a,mod_b"\n'
    assert gitlab_ci._yaml_scalar(text, "ENABLE_RUFF") == "true"
    assert gitlab_ci._yaml_scalar(text, "IGNORE_LINTERS") == "mod_a,mod_b"


def test_yaml_scalar_missing_key_returns_none():
    assert gitlab_ci._yaml_scalar("variables:\n  X: 1\n", "ENABLE_RUFF") is None


def test_rewrite_ruff_ignore_replaces_extend_exclude_line():
    toml = 'line-length = 180\nextend-exclude = ["old/**"]\ntarget-version = "py310"\n'
    rewritten = gitlab_ci.rewrite_ruff_ignore(toml, "mod_a,mod_b")
    assert 'extend-exclude = ["mod_a/**", "mod_b/**"]' in rewritten
    assert 'line-length = 180' in rewritten
    assert 'target-version = "py310"' in rewritten


def _lint_env(monkeypatch, ci_yaml, dockerfile="FROM x\nRUN pip install ruff==0.15.20\n",
              ruff_toml='extend-exclude = ["old/**"]\n', uvx_stdout="[]", changed_files=()):
    files = {
        "pipelines/sun-sca.yml": ci_yaml,
        "config/docker/Dockerfile.cicd-runner": dockerfile,
        "config/linters/ruff/ruff.toml": ruff_toml,
    }

    def fake_api_request(token, method, url, data=None, **kw):
        return {"id": 90, "ci_config_path": "pipelines/sun-sca.yml@infra/cicd-pipeline-template:sca"}

    def fake_raw(token, url):
        for name, content in files.items():
            if urllib.parse.quote(name, safe="") in url:
                return content.encode("utf-8")
        raise AssertionError(f"unexpected raw URL {url}")

    def fake_run(args, cwd=None, capture_output=None, text=None, check=None, **kw):
        if args[0] == "uvx":
            return subprocess.CompletedProcess(args, 0, stdout=uvx_stdout, stderr="")
        if args[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(args, 0, stdout="\n".join(changed_files), stderr="")
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "api_request_raw", fake_raw)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 90)
    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn",
                                  "addons_dir": "/repo/addons"})


def test_cmd_lint_disabled_returns_skipped(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "false"\n')
    assert gitlab_ci.cmd_lint(target="dev") == {"skipped": True}


def test_cmd_lint_unparsable_version_exits_10(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n', dockerfile="FROM x\n")
    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_cmd_lint_no_findings(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n  IGNORE_LINTERS: ""\n',
              uvx_stdout="[]")
    result = gitlab_ci.cmd_lint(target="dev")
    assert result == {"ruff_version": "0.15.20", "findings": []}


def test_cmd_lint_findings_flag_in_branch_and_exit_1(monkeypatch, capsys):
    findings_json = json.dumps([
        {"filename": "/repo/addons/module_a/models/x.py", "location": {"row": 12},
         "code": "F401", "message": "unused import"},
        {"filename": "/repo/addons/module_b/models/y.py", "location": {"row": 3},
         "code": "E501", "message": "line too long"},
    ])
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n',
              uvx_stdout=findings_json, changed_files=["addons/module_a/models/x.py"])

    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 1
    printed = json.loads(capsys.readouterr().out)
    by_file = {f["file"]: f["in_branch"] for f in printed["findings"]}
    assert by_file["/repo/addons/module_a/models/x.py"] is True
    assert by_file["/repo/addons/module_b/models/y.py"] is False


def test_rewrite_ruff_ignore_handles_multiline_array():
    toml = 'line-length = 180\nextend-exclude = [\n  "old/**",\n  "other/**",\n]\ntarget-version = "py310"\n'
    rewritten = gitlab_ci.rewrite_ruff_ignore(toml, "mod_a,mod_b")
    assert 'extend-exclude = ["mod_a/**", "mod_b/**"]' in rewritten
    assert 'line-length = 180' in rewritten
    assert 'target-version = "py310"' in rewritten
    # Verify no orphan brackets or dangling lines
    assert '"old/**"' not in rewritten
    assert '"other/**"' not in rewritten


def test_cmd_lint_uvx_not_found_exits_10(monkeypatch):
    def fake_run(args, cwd=None, capture_output=None, text=None, check=None, **kw):
        if args[0] == "uvx":
            raise FileNotFoundError("uvx not found")
        raise AssertionError(f"unexpected subprocess call: {args}")

    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n')
    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)

    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code != 0  # Should be 10 (message-only exit)
        assert isinstance(e.code, str)
        assert "uvx" in e.code.lower()


def test_cmd_lint_ruff_invalid_json_exits_10(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n',
              uvx_stdout="not valid json")

    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code != 0  # Should be 10 (message-only exit)
        assert isinstance(e.code, str)
        assert "json" in e.code.lower()


def test_cmd_lint_unresolvable_upstream_ref_exits_10(monkeypatch):
    _lint_env(monkeypatch, ci_yaml='variables:\n  ENABLE_RUFF: "true"\n')

    def fake_run(args, cwd=None, capture_output=None, text=None, check=None, **kw):
        if args[0] == "uvx":
            return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")
        if args[:2] == ["git", "diff"]:
            # a fresh clone that never fetched upstream/dev: git exits 128, empty stdout
            return subprocess.CompletedProcess(
                args, 128, stdout="", stderr="fatal: ambiguous argument 'upstream/dev...HEAD'")
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)

    try:
        gitlab_ci.cmd_lint(target="dev")
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert isinstance(e.code, str)  # message-only exit -> 10, not silent in_branch: false
        assert "git fetch upstream dev" in e.code


def test_cmd_retry_job(monkeypatch):
    def fake_api_request(token, method, url, data=None, **kw):
        assert method == "POST"
        assert url == "https://gitlab.vdx.vn/api/v4/projects/21/jobs/999/retry"
        return {"id": 1000, "pipeline": {"id": 56}}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})

    result = gitlab_ci.cmd_retry_job(project_id=21, job_id=999)
    assert result["job_id"] == 1000
    assert result["pipeline_id"] == 56
    assert isinstance(result["since"], int)


def test_cmd_notify_sends_and_reports_sent(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data)
        seen["headers"] = dict(req.headers)
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn",
                                  "telegram_channel": "-100", "telegram_token": "BOTTOK"})

    result = gitlab_ci.cmd_notify(text="MR !3 green")
    assert result == {"telegram": "sent"}
    assert seen["url"] == "https://api.telegram.org/botBOTTOK/sendMessage"
    assert seen["body"] == {"chat_id": "-100", "text": "MR !3 green"}
    assert seen["headers"]["User-agent"] == gitlab_ci.USER_AGENT


def test_cmd_notify_failure_reports_reason_exit_0(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn",
                                  "telegram_channel": "-100", "telegram_token": "BOTTOK"})

    result = gitlab_ci.cmd_notify(text="x")
    assert result["telegram"].startswith("failed:")
    assert "BOTTOK" not in json.dumps(result)  # token never printed


def test_cmd_notify_missing_config_reports_failed(monkeypatch):
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    result = gitlab_ci.cmd_notify(text="x")
    assert result["telegram"].startswith("failed:")


def test_cmd_clean_removes_only_matching_pipeline_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path)
    d1 = tmp_path / "21" / "55"
    d1.mkdir(parents=True)
    (d1 / "100.json").write_text(json.dumps({"merge_request": {"iid": 7}}), encoding="utf-8")
    d2 = tmp_path / "21" / "56"
    d2.mkdir(parents=True)
    (d2 / "101.json").write_text(json.dumps({"merge_request": {"iid": 8}}), encoding="utf-8")

    result = gitlab_ci.cmd_clean(mr_iid=7)

    assert result == {"removed": [55]}
    assert not d1.exists()
    assert d2.exists()


def test_cmd_clean_no_events_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "nope")
    assert gitlab_ci.cmd_clean(mr_iid=7) == {"removed": []}


def test_read_env_file_parses_key_value_lines(tmp_path):
    p = tmp_path / ".env"
    p.write_text("TUNNEL_TOKEN=abc\n# comment\nHOOK_HOSTNAME=x.vdx.vn\n\n", encoding="utf-8")
    assert gitlab_ci._read_env_file(p) == {"TUNNEL_TOKEN": "abc", "HOOK_HOSTNAME": "x.vdx.vn"}


def test_read_env_file_missing_returns_empty(tmp_path):
    assert gitlab_ci._read_env_file(tmp_path / "nope") == {}


def test_write_env_file_sets_permissions_600(tmp_path):
    p = tmp_path / ".env"
    gitlab_ci._write_env_file(p, {"A": "1", "B": "2"})
    assert p.read_text(encoding="utf-8") == "A=1\nB=2\n"
    assert (p.stat().st_mode & 0o777) == 0o600


def _checks_env(monkeypatch, tmp_path, git_root="/repo", gitlab_url="https://gitlab.vdx.vn",
                 remotes=None, telegram=None):
    remotes = remotes if remotes is not None else {
        "origin": "https://gitlab.vdx.vn/truong/sca.git",
        "upstream": "https://gitlab.vdx.vn/sungroup/sca",
    }
    cfg = {"git_root": git_root, "gitlab_url": gitlab_url,
           "addons_dir": git_root + "/addons"}
    if telegram:
        cfg.update(telegram)

    def fake_git_remote_url(remote, root):
        return remotes.get(remote)

    monkeypatch.setattr(gitlab_ci, "load_project_config", lambda: cfg)
    monkeypatch.setattr(gitlab_ci, "_git_remote_url", fake_git_remote_url)
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "docker" / "events")
    return cfg


def test_check_a_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ok, _ = gitlab_ci._check_a()
    assert ok is True


def test_check_a_fails_without_upstream_remote(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path, remotes={"origin": "https://gitlab.vdx.vn/truong/sca.git"})
    ok, detail = gitlab_ci._check_a()
    assert ok is False and "upstream" in detail


def test_check_a_fails_on_host_mismatch(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path, remotes={
        "origin": "https://gitlab.vdx.vn/truong/sca.git",
        "upstream": "https://gitlab.other.example/sungroup/sca",
    })
    ok, detail = gitlab_ci._check_a()
    assert ok is False and "host" in detail


def test_check_b_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, **kw: {"id": 1})
    ok, _ = gitlab_ci._check_b()
    assert ok is True


def test_check_b_fails_on_auth_error(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)

    def boom(token, method, url, **kw):
        raise SystemExit("error: GitLab API GET .../user returned 401: ...")

    monkeypatch.setattr(gitlab_ci, "api_request", boom)
    ok, detail = gitlab_ci._check_b()
    assert ok is False and "401" in detail


def test_check_c_reports_missing_keys(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"TUNNEL_TOKEN": "t"})
    ok, detail = gitlab_ci._check_c()
    assert ok is False
    assert "HOOK_HOSTNAME" in detail


def test_check_c_ok_when_all_keys_present(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env",
                               {k: "x" for k in gitlab_ci.ENV_ALL_KEYS})
    ok, _ = gitlab_ci._check_c()
    assert ok is True


def test_check_d_reports_missing_services(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)

    def fake_run(args, **kw):
        assert args[:2] == ["docker", "compose"]
        out = '{"Service": "cloudflared", "State": "running"}\n'
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    ok, detail = gitlab_ci._check_d()
    assert ok is False and "listener" in detail


def test_check_d_ok_when_both_running(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)

    def fake_run(args, **kw):
        out = ('{"Service": "cloudflared", "State": "running"}\n'
               '{"Service": "listener", "State": "running"}\n')
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(gitlab_ci.subprocess, "run", fake_run)
    ok, _ = gitlab_ci._check_d()
    assert ok is True


def test_check_e_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, **kw: [
        {"url": "https://x.vdx.vn/hook", "pipeline_events": True, "alert_status": "executable"}])
    ok, _ = gitlab_ci._check_e()
    assert ok is True


def test_check_e_fails_wrong_alert_status(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    (tmp_path / "docker").mkdir()
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, **kw: [
        {"url": "https://x.vdx.vn/hook", "pipeline_events": True, "alert_status": "disabled"}])
    ok, detail = gitlab_ci._check_e()
    assert ok is False and "alert_status" in detail


def test_check_f_ok_when_uvx_on_path(monkeypatch):
    monkeypatch.setattr(gitlab_ci.shutil, "which", lambda name: "/usr/bin/uvx")
    assert gitlab_ci._check_f() == (True, "ok")


def test_check_f_fails_when_uvx_missing(monkeypatch):
    monkeypatch.setattr(gitlab_ci.shutil, "which", lambda name: None)
    ok, detail = gitlab_ci._check_f()
    assert ok is False and "uvx" in detail


def test_check_g_ok(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path, telegram={"telegram_channel": "-1", "telegram_token": "BOT"})

    def fake_urlopen(req, timeout=None):
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(gitlab_ci.urllib.request, "urlopen", fake_urlopen)
    ok, _ = gitlab_ci._check_g()
    assert ok is True


def test_check_g_fails_missing_config(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ok, detail = gitlab_ci._check_g()
    assert ok is False and "telegram" in detail


def test_check_h_detects_last_delivery_change(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ev_dir = tmp_path / "docker" / "events"
    ev_dir.mkdir(parents=True)
    (tmp_path / "docker").mkdir(exist_ok=True)
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    (ev_dir / ".last_delivery").write_text("before", encoding="utf-8")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)

    calls = {"n": 0}

    def fake_api_request(token, method, url, data=None, **kw):
        if method == "GET":
            return [{"id": 9, "url": "https://x.vdx.vn/hook"}]
        calls["n"] += 1
        (ev_dir / ".last_delivery").write_text("after", encoding="utf-8")
        return {}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    ok, _ = gitlab_ci._check_h(sleep_fn=lambda s: None, now_fn=lambda: 0)
    assert ok is True
    assert calls["n"] == 1


def test_check_h_times_out_without_delivery(monkeypatch, tmp_path):
    _checks_env(monkeypatch, tmp_path)
    ev_dir = tmp_path / "docker" / "events"
    ev_dir.mkdir(parents=True)
    (tmp_path / "docker").mkdir(exist_ok=True)
    gitlab_ci._write_env_file(tmp_path / "docker" / ".env", {"HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path", lambda remote, root: "sungroup/sca")
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id", lambda token, url, path: 21)
    monkeypatch.setattr(gitlab_ci, "api_request", lambda token, method, url, data=None, **kw:
                         [{"id": 9, "url": "https://x.vdx.vn/hook"}] if method == "GET" else {})

    clock = {"t": 0.0}
    ok, detail = gitlab_ci._check_h(
        sleep_fn=lambda s: clock.__setitem__("t", clock["t"] + s), now_fn=lambda: clock["t"])
    assert ok is False and "15s" in detail


def _stub_all_checks(monkeypatch, ok=True):
    for check_id in "abcdefg":
        monkeypatch.setattr(gitlab_ci, f"_check_{check_id}", lambda: (ok, "ok" if ok else "bad"))
    monkeypatch.setattr(gitlab_ci, "_check_h", lambda **kw: (ok, "ok" if ok else "bad"))


def test_run_checks_skips_h_when_a_fails(monkeypatch):
    monkeypatch.setattr(gitlab_ci, "_check_a", lambda: (False, "no config"))
    for check_id in "bcdefg":
        monkeypatch.setattr(gitlab_ci, f"_check_{check_id}", lambda: (True, "ok"))
    called = {"h": False}
    monkeypatch.setattr(gitlab_ci, "_check_h", lambda **kw: called.__setitem__("h", True) or (True, "ok"))

    result = gitlab_ci._run_checks()

    assert result["ok"] is False
    assert called["h"] is False
    h_row = next(c for c in result["checks"] if c["id"] == "h")
    assert h_row["ok"] is False and "skipped" in h_row["detail"]


def test_run_checks_all_ok(monkeypatch):
    _stub_all_checks(monkeypatch, ok=True)
    result = gitlab_ci._run_checks()
    assert result["ok"] is True
    assert all(c["fix"] is None for c in result["checks"])


def test_cmd_check_setup_exits_11_on_failure(monkeypatch, capsys):
    _stub_all_checks(monkeypatch, ok=False)
    try:
        gitlab_ci.cmd_check_setup()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 11
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_cmd_check_setup_returns_ok(monkeypatch):
    _stub_all_checks(monkeypatch, ok=True)
    assert gitlab_ci.cmd_check_setup()["ok"] is True


def test_cmd_setup_missing_required_env_exits_11(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    (tmp_path / "docker").mkdir()
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    try:
        gitlab_ci.cmd_setup()
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 11


def test_cmd_setup_fills_missing_keys_and_creates_hook(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "docker" / "events")
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    gitlab_ci._write_env_file(docker_dir / ".env",
                               {"TUNNEL_TOKEN": "tok", "HOOK_HOSTNAME": "x.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path",
                         lambda remote, root: {"origin": "truong/sca", "upstream": "sungroup/sca"}[remote])
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id",
                         lambda token, url, path: {"truong/sca": 90, "sungroup/sca": 21}[path])
    monkeypatch.setattr(gitlab_ci.subprocess, "run",
                         lambda args, **kw: subprocess.CompletedProcess(args, 0, stdout="", stderr=""))
    api_calls = []

    def fake_api_request(token, method, url, data=None, **kw):
        api_calls.append((method, url, data))
        if method == "GET":
            return []
        return {"id": 9}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "_run_checks", lambda: {"ok": True, "checks": []})

    result = gitlab_ci.cmd_setup()

    env = gitlab_ci._read_env_file(docker_dir / ".env")
    assert set(gitlab_ci.ENV_AUTO) <= env.keys()
    assert result["hook"] == "created"
    assert result["hook_id"] == 9
    assert sorted(result["env_added"]) == sorted(gitlab_ci.ENV_AUTO)
    post_calls = [c for c in api_calls if c[0] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0][2]["pipeline_events"] is True
    assert post_calls[0][2]["push_events"] is False


def test_cmd_setup_updates_existing_hook(monkeypatch, tmp_path):
    monkeypatch.setattr(gitlab_ci, "skill_dir", lambda: tmp_path)
    monkeypatch.setattr(gitlab_ci, "events_dir", lambda: tmp_path / "docker" / "events")
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir()
    gitlab_ci._write_env_file(docker_dir / ".env", {k: "x" for k in gitlab_ci.ENV_ALL_KEYS})
    monkeypatch.setattr(gitlab_ci, "load_project_config",
                         lambda: {"git_root": "/repo", "gitlab_url": "https://gitlab.vdx.vn"})
    monkeypatch.setattr(gitlab_ci, "resolve_gitlab_token", lambda host: "TOK")
    monkeypatch.setattr(gitlab_ci, "git_remote_project_path",
                         lambda remote, root: {"origin": "truong/sca", "upstream": "sungroup/sca"}[remote])
    monkeypatch.setattr(gitlab_ci, "gitlab_project_id",
                         lambda token, url, path: {"truong/sca": 90, "sungroup/sca": 21}[path])
    monkeypatch.setattr(gitlab_ci.subprocess, "run",
                         lambda args, **kw: subprocess.CompletedProcess(args, 0, stdout="", stderr=""))

    def fake_api_request(token, method, url, data=None, **kw):
        if method == "GET":
            return [{"id": 5, "url": "https://x/hook"}]
        return {}

    monkeypatch.setattr(gitlab_ci, "api_request", fake_api_request)
    monkeypatch.setattr(gitlab_ci, "_run_checks", lambda: {"ok": True, "checks": []})

    result = gitlab_ci.cmd_setup()
    assert result["hook"] == "updated"
    assert result["hook_id"] == 5
    assert result["env_added"] == []
