import http.client
import importlib
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docker"))


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "SECRET")
    monkeypatch.setenv("FORK_PROJECT_ID", "90")
    monkeypatch.setenv("EVENTS_DIR", str(tmp_path))
    if "listener" in sys.modules:
        importlib.reload(sys.modules["listener"])
    import listener
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), listener.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, tmp_path
    httpd.shutdown()
    thread.join()


def _post(port, path, body, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("POST", path, body=body, headers=headers or {})
    resp = conn.getresponse()
    status = resp.status
    resp.read()
    conn.close()
    return status


def test_missing_token_401(server):
    httpd, _ = server
    assert _post(httpd.server_address[1], "/hook", b"{}") == 401


def test_wrong_token_401(server):
    httpd, _ = server
    assert _post(httpd.server_address[1], "/hook", b"{}", {"X-Gitlab-Token": "nope"}) == 401


def test_wrong_method_404(server):
    httpd, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
    conn.request("GET", "/hook")
    assert conn.getresponse().status == 404


def test_wrong_path_404(server):
    httpd, _ = server
    assert _post(httpd.server_address[1], "/other", b"{}", {"X-Gitlab-Token": "SECRET"}) == 404


def test_oversize_body_413(server):
    httpd, _ = server
    big = b"x" * (5 * 1024 * 1024 + 1)
    assert _post(httpd.server_address[1], "/hook", big, {"X-Gitlab-Token": "SECRET"}) == 413


def test_authenticated_delivery_rewrites_last_delivery(server):
    httpd, events_dir = server
    assert _post(httpd.server_address[1], "/hook", b"{}", {"X-Gitlab-Token": "SECRET"}) == 200
    assert (events_dir / ".last_delivery").is_file()


def test_fork_pipeline_event_stored(server):
    httpd, events_dir = server
    payload = json.dumps({
        "object_kind": "pipeline",
        "object_attributes": {"id": 55, "sha": "abc", "status": "success"},
        "merge_request": {"iid": 7, "source_project_id": 90},
        "project": {"id": 21},
    }).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    files = list((events_dir / "21" / "55").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["object_attributes"]["sha"] == "abc"


def test_other_source_project_discarded(server):
    httpd, events_dir = server
    payload = json.dumps({
        "object_kind": "pipeline", "object_attributes": {"id": 55},
        "merge_request": {"iid": 7, "source_project_id": 999},
        "project": {"id": 21},
    }).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    assert not (events_dir / "21").exists()


def test_no_merge_request_discarded(server):
    httpd, events_dir = server
    payload = json.dumps({"object_kind": "pipeline", "object_attributes": {"id": 55},
                           "project": {"id": 21}}).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    assert not (events_dir / "21").exists()


def test_non_pipeline_event_discarded(server):
    httpd, events_dir = server
    payload = json.dumps({"object_kind": "push"}).encode("utf-8")
    assert _post(httpd.server_address[1], "/hook", payload, {"X-Gitlab-Token": "SECRET"}) == 200
    assert list(events_dir.iterdir()) == [events_dir / ".last_delivery"]
