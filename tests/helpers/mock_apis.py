"""Shared requests-mock helpers for KCWorks communities + import APIs."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

DEFAULT_HOST = "http://kcworks.test"


def _request_json(request: Any) -> dict[str, Any]:
    """Parse a JSON request body from a requests-mock request.

    Args:
        request: A requests-mock request object.

    Returns:
        Parsed JSON object, or ``{}`` when the body is empty.
    """
    body = request.body
    if body is None:
        return {}
    if isinstance(body, bytes):
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))
    if isinstance(body, str):
        if not body:
            return {}
        return json.loads(body)
    return {}


def register_mock_apis(
    requests_mock: Any,
    *,
    extra_state: dict[str, Any] | None = None,
    host: str = DEFAULT_HOST,
) -> dict[str, Any]:
    """Register community + import API endpoints on ``requests_mock``.

    Args:
        requests_mock: The pytest ``requests_mock`` fixture (or an ``Mocker``).
        extra_state: Optional overrides merged into the mutable mock state
            (e.g. ``get_status``, ``post_community_status``, pre-seeded
            ``communities``).
        host: Base host for mocked URLs (no path).

    Returns:
        Dict with ``communities_url``, ``import_url``, ``host``, and mutable
        ``state`` (``communities``, ``imports``, ``join_requests``).
    """
    state: dict[str, Any] = {
        "communities": {},
        "imports": [],
        "join_requests": [],
    }
    if extra_state:
        state.update(extra_state)

    communities_url = f"{host.rstrip('/')}/api/communities"
    import_url = f"{host.rstrip('/')}/api/import"

    def get_community(request: Any, context: Any) -> dict[str, Any]:
        get_status = state.get("get_status")
        if get_status is not None and get_status != 200:
            context.status_code = get_status
            return {"message": "forced error"}
        path = urlparse(request.url).path
        key = path[len("/api/communities/") :].rstrip("/")
        for community in state["communities"].values():
            if community["slug"] == key or community["id"] == key:
                context.status_code = 200
                return community
        context.status_code = 404
        return {"message": "Not found"}

    def post_community(request: Any, context: Any) -> dict[str, Any]:
        post_status = state.get("post_community_status", 201)
        data = _request_json(request)
        if post_status not in (200, 201):
            context.status_code = post_status
            return {"message": "create failed"}
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
        context.status_code = 201
        return community

    def post_join(request: Any, context: Any) -> dict[str, Any]:
        join_status = state.get("join_status", 201)
        data = _request_json(request)
        if join_status not in (200, 201):
            context.status_code = join_status
            return {"message": "join failed"}
        child_id = data.get("community_id")
        path = urlparse(request.url).path
        parent_id = path.split("/")[-3]
        child = next(
            (c for c in state["communities"].values() if c["id"] == child_id),
            None,
        )
        parent = next(
            (c for c in state["communities"].values() if c["id"] == parent_id),
            None,
        )
        if child and parent:
            child["parent"] = {"id": parent["id"], "slug": parent["slug"]}
        state["join_requests"].append(data)
        context.status_code = 201
        return {
            "id": "req-1",
            "status": state.get("join_result_status", "accepted"),
            "type": "subcommunity",
        }

    def post_import(request: Any, context: Any) -> dict[str, Any]:
        path = urlparse(request.url).path
        slug = path[len("/api/import/") :].rstrip("/")
        body = request.body or b""
        if isinstance(body, str):
            body = body.encode("utf-8")
        state["imports"].append({"slug": slug, "body": body})
        import_status = state.get("import_status", 201)
        context.status_code = import_status
        if import_status == 201:
            return {
                "data": [
                    {
                        "item_index": 0,
                        "record_id": f"rec-{slug}",
                        "record_url": f"https://example.com/{slug}",
                    }
                ],
                "errors": [],
                "message": "Import completed.",
            }
        if import_status == 207:
            return {
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
            }
        return {
            "data": [],
            "errors": [
                {
                    "item_index": 0,
                    "errors": [{"field": "x", "message": "y"}, "raw"],
                }
            ],
            "message": "failed",
        }

    def put_community(request: Any, context: Any) -> dict[str, Any]:
        put_status = state.get("put_status", 200)
        path = urlparse(request.url).path
        key = path[len("/api/communities/") :].rstrip("/")
        data = _request_json(request)
        if put_status != 200:
            context.status_code = put_status
            return {"message": "put failed"}
        for community in state["communities"].values():
            if community["id"] == key or community["slug"] == key:
                if "children" in data:
                    community["children"] = data["children"]
                community["revision_id"] = community.get("revision_id", 1) + 1
                context.status_code = 200
                return community
        context.status_code = 404
        return {"message": "Not found"}

    requests_mock.get(
        re.compile(rf"{re.escape(communities_url)}/[^/]+$"),
        json=get_community,
    )
    requests_mock.post(
        re.compile(rf"{re.escape(communities_url)}$"),
        json=post_community,
    )
    requests_mock.post(
        re.compile(rf"{re.escape(communities_url)}/.+/actions/join-request$"),
        json=post_join,
    )
    requests_mock.put(
        re.compile(rf"{re.escape(communities_url)}/[^/]+$"),
        json=put_community,
    )
    requests_mock.post(
        re.compile(rf"{re.escape(import_url)}/.+"),
        json=post_import,
    )

    return {
        "communities_url": communities_url,
        "import_url": import_url,
        "state": state,
        "host": host,
    }


def register_import_endpoint(
    requests_mock: Any,
    *,
    import_url: str = f"{DEFAULT_HOST}/api/import",
    collection_id: str | None = None,
    response_body: dict[str, Any] | str | None = None,
    status_code: int = 201,
    content_type: str = "application/json",
) -> str:
    """Register a single-collection import POST response.

    Args:
        requests_mock: The pytest ``requests_mock`` fixture.
        import_url: Import API base URL (no collection segment).
        collection_id: When set, match only that collection URL. When
            ``None``, match any collection under ``import_url``.
        response_body: JSON dict, plain text, or ``None`` for a minimal
            success payload.
        status_code: HTTP status to return.
        content_type: Used when ``response_body`` is a string.

    Returns:
        The ``import_url`` base (for env wiring).
    """
    if collection_id is None:
        url: str | re.Pattern[str] = re.compile(rf"{re.escape(import_url.rstrip('/'))}/.+")
    else:
        url = f"{import_url.rstrip('/')}/{collection_id}"

    if isinstance(response_body, str):
        requests_mock.post(
            url,
            text=response_body,
            status_code=status_code,
            headers={"Content-Type": content_type},
        )
    else:
        body = response_body or {
            "data": [
                {
                    "item_index": 0,
                    "record_id": "test-123",
                    "record_url": "https://example.com/records/test-123",
                }
            ],
            "errors": [],
            "message": "Import completed.",
        }
        requests_mock.post(url, json=body, status_code=status_code)

    return import_url
