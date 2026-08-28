from sync_engine.queue.base import SyncQueue


class InMemoryQueue(SyncQueue):
    """In-memory SyncQueue implementation — for tests only, no persistence."""

    def __init__(self) -> None:
        self._messages: dict[str, dict] = {}

    def push(self, message_id: str, payload: dict) -> None:
        self._messages[message_id] = payload

    def pull(self, max_messages: int) -> list[tuple[str, dict]]:
        return list(self._messages.items())[:max_messages]

    def delete(self, message_id: str) -> None:
        self._messages.pop(message_id, None)
