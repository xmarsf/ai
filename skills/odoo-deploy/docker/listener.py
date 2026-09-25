#!/usr/bin/env python3
"""Stdlib webhook receiver for odoo-deploy. Only POST /hook is served;
authenticated deliveries are stored as one file per pipeline event under
EVENTS_DIR for gitlab_ci.py's `wait` to scan — this process never talks to
the GitLab API itself."""
from __future__ import annotations

import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
FORK_PROJECT_ID = int(os.environ["FORK_PROJECT_ID"])
EVENTS_DIR = Path(os.environ.get("EVENTS_DIR", "/events"))
MAX_BODY_BYTES = 5 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/hook":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            self.send_response(413)
            self.end_headers()
            # Drain the connection in chunks to avoid broken pipe
            remaining = length
            chunk_size = 64 * 1024
            while remaining > 0:
                chunk = self.rfile.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            return
        body = self.rfile.read(length)

        if not hmac.compare_digest(self.headers.get("X-Gitlab-Token", ""), WEBHOOK_SECRET):
            self.send_response(401)
            self.end_headers()
            return

        # Store the real event first: a failure writing the delivery marker
        # (only check `h` reads it) must not cost a pipeline event.
        self._store_event(body)
        self._record_delivery()
        self.send_response(200)
        self.end_headers()

    def _record_delivery(self) -> None:
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        marker = EVENTS_DIR / ".last_delivery"
        # Unique per request: ThreadingHTTPServer serves concurrent deliveries,
        # and a shared tmp name lets one thread's os.replace consume another's.
        received_ns = time.time_ns()
        tmp = EVENTS_DIR / f".last_delivery.{received_ns}.tmp"
        tmp.write_text(str(received_ns), encoding="utf-8")
        os.replace(tmp, marker)

    def _store_event(self, body: bytes) -> None:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return
        if data.get("object_kind") != "pipeline":
            return
        mr = data.get("merge_request")
        if not mr or mr.get("source_project_id") != FORK_PROJECT_ID:
            return
        project_id = (data.get("project") or {}).get("id")
        pipeline_id = (data.get("object_attributes") or {}).get("id")
        if project_id is None or pipeline_id is None:
            return
        received_ns = time.time_ns()
        target_dir = EVENTS_DIR / str(project_id) / str(pipeline_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = target_dir / f".{received_ns}.tmp"
        tmp_path.write_bytes(body)
        os.replace(tmp_path, target_dir / f"{received_ns}.json")

    def log_message(self, fmt, *args) -> None:
        pass  # default logging echoes the request line; keep it quiet


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
