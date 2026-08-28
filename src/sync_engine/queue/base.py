from abc import ABC, abstractmethod


class SyncQueue(ABC):
    """Boundary-crossing transport: a producer pushes, a consumer pulls.

    Per ADR-004, the same interface is used on both sides of a boundary
    crossing — one SyncQueue instance in push mode for a producer, another
    instance in pull mode for the consumer on the other side. There is no
    separate inbound/outbound ABC.

    A message is removed only via delete(), called after the operation that
    depended on it has committed — never before (CLAUDE.md invariant #2,
    "acknowledge after commit", extended to message acknowledgement).
    """

    @abstractmethod
    def push(self, message_id: str, payload: dict) -> None:
        """Publish payload under message_id."""

    @abstractmethod
    def pull(self, max_messages: int) -> list[tuple[str, dict]]:
        """Return up to max_messages pending (message_id, payload) pairs."""

    @abstractmethod
    def delete(self, message_id: str) -> None:
        """Acknowledge and remove message_id.

        Call only after the consumer's own commit has succeeded — never
        speculatively, so a failure before that point leaves the message on
        the queue for redelivery.
        """
