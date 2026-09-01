"""Shared mock KCWorks communities + import HTTP server for tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse


def make_combined_handler(state: dict[str, Any]):
    """Build a handler for communities + import endpoints.

    Args:
        state: Mutable dict with keys ``communities``, ``imports``,
            ``join_requests``. Optional ``get_status``, ``post_community_status``,
            ``join_status``, ``put_status``, ``import_status`` override responses.

    Returns:
        A ``BaseHTTPRequestHandler`` subclass.
    """

    class Handler(BaseHTTPRequestHandler):
        def _read_json(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _send(self, status: int, payload: dict | list | str):
            if isinstance(payload, (dict, list)):
                body = json.dumps(payload).encode("utf-8")
                content_type = "application/json"
            else:
                body = str(payload).encode("utf-8")
                content_type = "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            get_status = state.get("get_status")
            if get_status is not None and get_status != 200:
                self._send(get_status, {"message": "forced error"})
                return
            prefix = "/api/communities/"
            if path.startswith(prefix) and "/actions/" not in path:
                key = path[len(prefix) :].rstrip("/")
                for community in state["communities"].values():
                    if community["slug"] == key or community["id"] == key:
                        self._send(200, community)
                        return
                self._send(404, {"message": "Not found"})
                return
            self._send(404, {"message": "Not found"})

        def do_POST(self):  # noqa: N802
            path = urlparse(self.path).path
            if path.rstrip("/") == "/api/communities":
                post_status = state.get("post_community_status", 201)
                if post_status not in (200, 201):
                    self._read_json()
                    self._send(post_status, {"message": "create failed"})
                    return
                data = self._read_json()
                slug = data.get("slug", "unnamed")
                community = {
                    "id": f"uuid-{slug}",
                    "slug": slug,
                    "metadata": data.get("metadata", {"title": slug}),
                    "access": data.get("access", {}),
                    "children": {"allow": False},
                    "revision_id": 1,
                }
                state["communities"][slug] = community
                self._send(201, community)
                return

            if path.endswith("/actions/join-request"):
                join_status = state.get("join_status", 201)
                data = self._read_json()
                if join_status not in (200, 201):
                    self._send(join_status, {"message": "join failed"})
                    return
                child_id = data.get("community_id")
                parent_id = path.split("/")[-3]
                child = next(
                    (
                        c
                        for c in state["communities"].values()
                        if c["id"] == child_id
                    ),
                    None,
                )
                parent = next(
                    (
                        c
                        for c in state["communities"].values()
                        if c["id"] == parent_id
                    ),
                    None,
                )
                if child and parent:
                    child["parent"] = {
                        "id": parent["id"],
                        "slug": parent["slug"],
                    }
                state["join_requests"].append(data)
                status_label = state.get("join_result_status", "accepted")
                self._send(
                    201,
                    {
                        "id": "req-1",
                        "status": status_label,
                        "type": "subcommunity",
                    },
                )
                return

            if path.startswith("/api/import/"):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b""
                slug = path[len("/api/import/") :].rstrip("/")
                state["imports"].append({"slug": slug, "body": body})
                import_status = state.get("import_status", 201)
                if import_status == 201:
                    self._send(
                        201,
                        {
                            "data": [
                                {
                                    "item_index": 0,
                                    "record_id": f"rec-{slug}",
                                    "record_url": f"https://example.com/{slug}",
                                }
                            ],
                            "errors": [],
                            "message": "Import completed.",
                        },
                    )
                    return
                if import_status == 207:
                    self._send(
                        207,
                        {
                            "data": [{"item_index": 0, "record_id": "ok"}],
                            "errors": [
                                {
                                    "item_index": 1,
                                    "errors": [
                                        {"field": "title", "message": "bad"},
                                        {"validation_error": "x"},
                                        {"file upload failures": ["a.pdf"]},
                                        "plain",
                                    ],
                                }
                            ],
                            "message": "Partial",
                        },
                    )
                    return
                self._send(
                    import_status,
                    {
                        "data": [],
                        "errors": [
                            {
                                "item_index": 0,
                                "errors": [
                                    {"field": "x", "message": "y"},
                                    "raw",
                                ],
                            }
                        ],
                        "message": "failed",
                    },
                )
                return

            self._send(404, {"message": "Not found"})

        def do_PUT(self):  # noqa: N802
            path = urlparse(self.path).path
            put_status = state.get("put_status", 200)
            prefix = "/api/communities/"
            if path.startswith(prefix):
                key = path[len(prefix) :].rstrip("/")
                data = self._read_json()
                if put_status != 200:
                    self._send(put_status, {"message": "put failed"})
                    return
                for community in state["communities"].values():
                    if community["id"] == key or community["slug"] == key:
                        if "children" in data:
                            community["children"] = data["children"]
                        community["revision_id"] = (
                            community.get("revision_id", 1) + 1
                        )
                        self._send(200, community)
                        return
                self._send(404, {"message": "Not found"})
                return
            self._send(404, {"message": "Not found"})

        def log_message(self, format, *args):  # noqa: A003
            pass

    return Handler


def start_mock_apis(
    *,
    extra_state: dict[str, Any] | None = None,
) -> tuple[HTTPServer, dict[str, Any]]:
    """Start a mock server; caller must ``server.shutdown()``.

    Returns:
        ``(server, info)`` where ``info`` has URL keys and ``state``.
    """
    state: dict[str, Any] = {
        "communities": {},
        "imports": [],
        "join_requests": [],
    }
    if extra_state:
        state.update(extra_state)
    handler = make_combined_handler(state)
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    info = {
        "communities_url": f"http://127.0.0.1:{port}/api/communities",
        "import_url": f"http://127.0.0.1:{port}/api/import",
        "state": state,
        "server": server,
    }
    return server, info
