from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sync_engine.exceptions import InvalidPayloadError


@dataclass(frozen=True)
class Change:
    """A single resource change, whichever channel it arrived through.

    ``updated_at`` is the source-side version of the resource and drives
    last-writer-wins ordering in the target (see ADR-004). ``authoritative``
    is True for changes read from REST, which arbitrates ties (ADR-001).
    """

    resource_id: str
    updated_at: datetime
    deleted: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    authoritative: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, authoritative: bool = False) -> "Change":
        """Parse ``{"id", "updated_at", "deleted"?, "data"?}`` into a Change.

        Raises:
            InvalidPayloadError: a required field is missing or malformed, or
                ``updated_at`` carries no timezone (naive and aware datetimes
                cannot be ordered against each other).
        """
        resource_id = raw.get("id")
        if not isinstance(resource_id, str) or not resource_id:
            raise InvalidPayloadError("Missing or invalid 'id'")

        raw_updated_at = raw.get("updated_at")
        if not isinstance(raw_updated_at, str):
            raise InvalidPayloadError(
                f"Missing or invalid 'updated_at' for {resource_id}"
            )
        try:
            updated_at = datetime.fromisoformat(raw_updated_at)
        except ValueError as exc:
            raise InvalidPayloadError(
                f"Unparseable 'updated_at' for {resource_id}: {raw_updated_at!r}"
            ) from exc
        if updated_at.tzinfo is None:
            raise InvalidPayloadError(
                f"'updated_at' must be timezone-aware for {resource_id}"
            )

        data = raw.get("data", {})
        if not isinstance(data, dict):
            raise InvalidPayloadError(f"'data' must be an object for {resource_id}")

        deleted = raw.get("deleted", False)
        if not isinstance(deleted, bool):
            raise InvalidPayloadError(f"'deleted' must be a boolean for {resource_id}")

        return cls(
            resource_id=resource_id,
            updated_at=updated_at,
            deleted=deleted,
            data=data,
            authoritative=authoritative,
        )
