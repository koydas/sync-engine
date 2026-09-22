from datetime import UTC, datetime, timedelta

import pytest

from sync_engine.models import Change
from sync_engine.target.memory import InMemoryTarget

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _change(
    updated_at: datetime = T0,
    data: dict | None = None,
    deleted: bool = False,
    authoritative: bool = False,
) -> Change:
    return Change(
        resource_id="r1",
        updated_at=updated_at,
        deleted=deleted,
        data=data if data is not None else {"v": 1},
        authoritative=authoritative,
    )


@pytest.fixture
def target() -> InMemoryTarget:
    return InMemoryTarget()


def test_apply_new_resource_is_stored(target: InMemoryTarget) -> None:
    assert target.apply(_change()) is True
    assert target.get("r1") == {"v": 1}


def test_apply_same_change_twice_second_is_noop(target: InMemoryTarget) -> None:
    target.apply(_change())

    assert target.apply(_change()) is False
    assert target.get("r1") == {"v": 1}


def test_apply_newer_change_overwrites(target: InMemoryTarget) -> None:
    target.apply(_change())

    assert target.apply(_change(T0 + timedelta(seconds=1), {"v": 2})) is True
    assert target.get("r1") == {"v": 2}


def test_apply_older_change_after_newer_is_ignored(target: InMemoryTarget) -> None:
    target.apply(_change(T0 + timedelta(seconds=1), {"v": 2}))

    assert target.apply(_change(T0, {"v": 1})) is False
    assert target.get("r1") == {"v": 2}


def test_apply_older_update_after_delete_does_not_resurrect(
    target: InMemoryTarget,
) -> None:
    target.apply(_change(T0 + timedelta(seconds=1), deleted=True))

    assert target.apply(_change(T0)) is False
    assert target.get("r1") is None


def test_apply_tie_authoritative_overwrites_webhook(target: InMemoryTarget) -> None:
    target.apply(_change(data={"v": "webhook"}))

    assert target.apply(_change(data={"v": "rest"}, authoritative=True)) is True
    assert target.get("r1") == {"v": "rest"}


def test_apply_tie_webhook_does_not_overwrite_authoritative(
    target: InMemoryTarget,
) -> None:
    target.apply(_change(data={"v": "rest"}, authoritative=True))

    assert target.apply(_change(data={"v": "webhook"})) is False
    assert target.get("r1") == {"v": "rest"}


def test_apply_tie_later_authoritative_read_overwrites_earlier_one(
    target: InMemoryTarget,
) -> None:
    target.apply(_change(data={"v": "first-read"}, authoritative=True))

    assert target.apply(_change(data={"v": "second-read"}, authoritative=True))
    assert target.get("r1") == {"v": "second-read"}


def test_apply_tie_identical_authoritative_read_is_noop(
    target: InMemoryTarget,
) -> None:
    target.apply(_change(authoritative=True))

    assert target.apply(_change(authoritative=True)) is False


def test_get_unknown_resource_returns_none(target: InMemoryTarget) -> None:
    assert target.get("missing") is None
