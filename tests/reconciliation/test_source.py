from datetime import UTC, datetime

import httpx
import pytest

from sync_engine.exceptions import ReconciliationError
from sync_engine.reconciliation.source import RestChangeSource

ITEM = {"id": "r1", "updated_at": "2026-01-01T12:00:00Z", "data": {"v": 1}}


def _source(handler) -> RestChangeSource:
    client = httpx.Client(
        base_url="https://api.test", transport=httpx.MockTransport(handler)
    )
    return RestChangeSource(client, "/resources")


def test_fetch_changes_with_since_sends_updated_since() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"items": [ITEM], "next_cursor": None})

    since = datetime(2026, 1, 1, 11, tzinfo=UTC)
    changes = list(_source(handler).fetch_changes(since))

    assert seen[0].params["updated_since"] == since.isoformat()
    assert [c.resource_id for c in changes] == ["r1"]
    assert changes[0].authoritative is True


def test_fetch_changes_without_since_requests_full_snapshot() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"items": []})

    assert list(_source(handler).fetch_changes(None)) == []
    assert "updated_since" not in seen[0].params


def test_fetch_changes_follows_cursor_until_exhausted() -> None:
    pages = {
        None: {"items": [ITEM], "next_cursor": "c2"},
        "c2": {"items": [{**ITEM, "id": "r2"}], "next_cursor": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("cursor")])

    changes = list(_source(handler).fetch_changes(None))

    assert [c.resource_id for c in changes] == ["r1", "r2"]


def test_fetch_changes_repeated_cursor_raises_reconciliation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [], "next_cursor": "loop"})

    with pytest.raises(ReconciliationError, match="cursor repeated"):
        list(_source(handler).fetch_changes(None))


@pytest.mark.parametrize(
    "cursor",
    [False, {}, [], "", 0, 42],
    ids=["false", "empty-object", "empty-list", "empty-string", "zero", "int"],
)
def test_fetch_changes_malformed_cursor_raises_reconciliation_error(cursor) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [ITEM], "next_cursor": cursor})

    with pytest.raises(ReconciliationError, match="Malformed pagination cursor"):
        list(_source(handler).fetch_changes(None))


def test_fetch_changes_missing_cursor_key_ends_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [ITEM]})

    assert [c.resource_id for c in _source(handler).fetch_changes(None)] == ["r1"]


def test_fetch_changes_http_error_status_raises_reconciliation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(ReconciliationError):
        list(_source(handler).fetch_changes(None))


def test_fetch_changes_transport_error_raises_reconciliation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ReconciliationError):
        list(_source(handler).fetch_changes(None))


def test_fetch_changes_non_json_body_raises_reconciliation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    with pytest.raises(ReconciliationError):
        list(_source(handler).fetch_changes(None))


@pytest.mark.parametrize(
    "body",
    [["not", "an", "object"], {"no_items": []}, {"items": "nope"}],
    ids=["list-body", "missing-items", "non-list-items"],
)
def test_fetch_changes_malformed_page_raises_reconciliation_error(body) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(ReconciliationError, match="Malformed page"):
        list(_source(handler).fetch_changes(None))


def test_fetch_changes_non_object_item_raises_reconciliation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": ["r1"]})

    with pytest.raises(ReconciliationError, match="Non-object item"):
        list(_source(handler).fetch_changes(None))


def test_fetch_changes_invalid_item_raises_reconciliation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [{"id": "r1"}]})

    with pytest.raises(ReconciliationError, match="Invalid item"):
        list(_source(handler).fetch_changes(None))
