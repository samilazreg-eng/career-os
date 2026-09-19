"""Synchronous in-memory publishing for Career events."""

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from events import CareerEvent
from template.singleton import Singleton


EventHandler = Callable[[CareerEvent], None]


@runtime_checkable
class EventPublisher(Protocol):
    """@brief Minimal event-publishing interface for business use cases."""

    def publish(self, event: CareerEvent) -> None:
        """
        @brief Publish one Career event.

        @param event Immutable event to deliver.
        """
        ...


@runtime_checkable
class EventBus(EventPublisher, Protocol):
    """@brief Event publisher that accepts string-keyed subscriptions."""

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        @brief Subscribe a handler to one exact event type.

        @param event_type Event type string to observe.
        @param handler Synchronous event handler.
        """
        ...


class EventDispatchError(RuntimeError):
    """@brief Aggregate failure raised after all event handlers have run."""

    def __init__(
        self,
        event: CareerEvent,
        failures: list[tuple[EventHandler, Exception]],
    ):
        """
        @brief Construct an aggregate event-delivery failure.

        @param event Event whose handlers failed.
        @param failures Handler and exception pairs in call order.
        """
        self.event = event
        self.failures = failures
        super().__init__(
            f"{len(failures)} handler(s) failed for event {event.event_type}"
        )


class InProcessEventBus:
    """@brief Deterministic synchronous event bus held entirely in memory."""

    def __init__(self) -> None:
        """@brief Construct an event bus without subscribers."""
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        @brief Subscribe a handler to one exact event type.

        @param event_type Event type string to observe.
        @param handler Synchronous event handler.
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: CareerEvent) -> None:
        """
        @brief Deliver an event synchronously to a snapshot of its handlers.

        @param event Immutable event to deliver.
        """
        handlers = tuple(self._handlers.get(event.event_type, ()))
        failures: list[tuple[EventHandler, Exception]] = []

        for handler in handlers:
            try:
                handler(event)
            except Exception as error:
                failures.append((handler, error))

        if failures:
            raise EventDispatchError(event, failures) from failures[0][1]


class CareerEventBus(InProcessEventBus, metaclass=Singleton):
    """@brief Application-wide in-process Career event bus singleton."""
