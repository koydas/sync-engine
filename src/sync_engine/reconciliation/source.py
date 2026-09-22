import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime

import httpx

from sync_engine.exceptions import InvalidPayloadError, ReconciliationError
from sync_engine.models import Change

logger = logging.getLogger(__name__)


class ChangeSource(ABC):
    """REST side of the hybrid architecture: the source of truth (ADR-001)."""

    @abstractmethod
    def fetch_changes(self, since: datetime | None) -> Iterator[Change]:
        """Yield every resource changed at or after since; all resources if None.

        Yielded changes are authoritative. Raises ReconciliationError on any
        transport, protocol or parsing failure.
        """


class RestChangeSource(ChangeSource):
    """Cursor-paginated REST source.

    Expected contract: ``GET <path>?updated_since=<iso8601>&cursor=<c>`` returns
    ``{"items": [{"id", "updated_at", "deleted"?, "data"?}, ...], "next_cursor": str | null}``.
    ``updated_since`` is omitted for a full snapshot.
    """

    def __init__(self, client: httpx.Client, path: str) -> None:
        self._client = client
        self._path = path

    def fetch_changes(self, since: datetime | None) -> Iterator[Change]:
        params: dict[str, str] = {}
        if since is not None:
            params["updated_since"] = since.isoformat()

        seen_cursors: set[str] = set()
        while True:
            body = self._get_page(params)
            for item in body["items"]:
                if not isinstance(item, dict):
                    raise ReconciliationError(
                        f"Non-object item in {self._path} response"
                    )
                try:
                    yield Change.from_dict(item, authoritative=True)
                except InvalidPayloadError as exc:
                    raise ReconciliationError(
                        f"Invalid item from {self._path}: {exc}"
                    ) from exc

            cursor = body.get("next_cursor")
            if not cursor:
                return
            if cursor in seen_cursors:
                raise ReconciliationError(
                    f"Pagination cursor repeated on {self._path}: {cursor}"
                )
            seen_cursors.add(cursor)
            params["cursor"] = cursor

    def _get_page(self, params: dict[str, str]) -> dict:
        try:
            response = self._client.get(self._path, params=params)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("REST fetch failed on %s: %s", self._path, exc)
            raise ReconciliationError(
                f"REST fetch failed on {self._path}: {exc}"
            ) from exc

        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            raise ReconciliationError(
                f"Malformed page from {self._path}: missing 'items' list"
            )
        return body
