from datetime import UTC, datetime

import pytest

from sync_engine.exceptions import InvalidPayloadError
from sync_engine.models import Change


def test_from_dict_full_payload_parses_all_fields() -> None:
    change = Change.from_dict(
        {
            "id": "r1",
            "updated_at": "2026-01-01T12:00:00+00:00",
            "deleted": True,
            "data": {"name": "a"},
        },
        authoritative=True,
    )

    assert change == Change(
        resource_id="r1",
        updated_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
        deleted=True,
        data={"name": "a"},
        authoritative=True,
    )


def test_from_dict_minimal_payload_defaults_to_live_non_authoritative() -> None:
    change = Change.from_dict({"id": "r1", "updated_at": "2026-01-01T12:00:00Z"})

    assert change.deleted is False
    assert change.data == {}
    assert change.authoritative is False


@pytest.mark.parametrize(
    "raw",
    [
        {"updated_at": "2026-01-01T12:00:00Z"},
        {"id": "", "updated_at": "2026-01-01T12:00:00Z"},
        {"id": 42, "updated_at": "2026-01-01T12:00:00Z"},
        {"id": "r1"},
        {"id": "r1", "updated_at": "not-a-date"},
        {"id": "r1", "updated_at": "2026-01-01T12:00:00"},
        {"id": "r1", "updated_at": "2026-01-01T12:00:00Z", "data": ["x"]},
        {"id": "r1", "updated_at": "2026-01-01T12:00:00Z", "deleted": "false"},
    ],
    ids=[
        "missing-id",
        "empty-id",
        "non-string-id",
        "missing-updated-at",
        "unparseable-updated-at",
        "naive-updated-at",
        "non-object-data",
        "non-bool-deleted",
    ],
)
def test_from_dict_invalid_payload_raises_invalid_payload_error(raw: dict) -> None:
    with pytest.raises(InvalidPayloadError):
        Change.from_dict(raw)
