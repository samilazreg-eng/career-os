"""Unit and singleton-isolation tests for the Career event bus."""

from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
import unittest

from inprocess_harness import InProcessCareer


SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

try:
    from eventbus import (
        EventBus,
        EventDispatchError,
        EventPublisher,
        InProcessEventBus,
    )
    from events import CommitInitiated, HeadSnapshot
finally:
    sys.path.pop(0)


def initiated_event(event_id: str = "event-1") -> CommitInitiated:
    """
    @brief Build an immutable event for event-bus tests.

    @param event_id Identifier used to distinguish publications.

    @return Commit-initiated test event.
    """
    return CommitInitiated(
        event_id=event_id,
        operation_id="operation-1",
        occurred_at=datetime(2026, 9, 19, 13, 14, 7, tzinfo=timezone.utc),
        head=HeadSnapshot(context="snt", mission="daedalux", thread=""),
    )


class InProcessEventBusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = InProcessEventBus()
        self.event = initiated_event()

    def test_implements_publisher_and_bus_protocols_structurally(self):
        self.assertIsInstance(self.bus, EventPublisher)
        self.assertIsInstance(self.bus, EventBus)

    def test_subscriber_receives_event_for_its_type(self):
        received = []
        self.bus.subscribe(self.event.event_type, received.append)

        self.bus.publish(self.event)

        self.assertEqual(received, [self.event])

    def test_subscriber_of_another_type_does_not_receive_event(self):
        received = []
        self.bus.subscribe("career.commit.completed", received.append)

        self.bus.publish(self.event)

        self.assertEqual(received, [])

    def test_subscribers_are_called_in_subscription_order(self):
        calls = []
        self.bus.subscribe(self.event.event_type, lambda event: calls.append("first"))
        self.bus.subscribe(self.event.event_type, lambda event: calls.append("second"))
        self.bus.subscribe(self.event.event_type, lambda event: calls.append("third"))

        self.bus.publish(self.event)

        self.assertEqual(calls, ["first", "second", "third"])

    def test_publishing_without_subscribers_is_a_no_op(self):
        self.assertIsNone(self.bus.publish(self.event))

    def test_all_handlers_run_and_failures_are_reported_in_call_order(self):
        calls = []
        first_failure = ValueError("first failure")
        second_failure = RuntimeError("second failure")

        def fail_first(event):
            calls.append("first")
            raise first_failure

        def succeed(event):
            calls.append("second")

        def fail_second(event):
            calls.append("third")
            raise second_failure

        def finish(event):
            calls.append("fourth")

        for handler in (fail_first, succeed, fail_second, finish):
            self.bus.subscribe(self.event.event_type, handler)

        with self.assertRaises(EventDispatchError) as raised:
            self.bus.publish(self.event)

        self.assertEqual(calls, ["first", "second", "third", "fourth"])
        self.assertIs(raised.exception.event, self.event)
        self.assertEqual(
            raised.exception.failures,
            [(fail_first, first_failure), (fail_second, second_failure)],
        )
        self.assertIs(raised.exception.__cause__, first_failure)

    def test_subscription_during_publish_applies_to_later_publications(self):
        calls = []

        def later(event):
            calls.append(("later", event.event_id))

        def subscribe_later(event):
            calls.append(("subscriber", event.event_id))
            self.bus.subscribe(event.event_type, later)

        self.bus.subscribe(self.event.event_type, subscribe_later)

        self.bus.publish(self.event)
        self.assertEqual(calls, [("subscriber", "event-1")])

        self.bus.publish(initiated_event("event-2"))
        self.assertEqual(
            calls,
            [
                ("subscriber", "event-1"),
                ("subscriber", "event-2"),
                ("later", "event-2"),
            ],
        )

    def test_base_exceptions_propagate_immediately_and_are_not_collected(self):
        for interruption in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(interruption=type(interruption).__name__):
                bus = InProcessEventBus()
                calls = []

                def interrupt(event, interruption=interruption):
                    calls.append("interrupt")
                    raise interruption

                bus.subscribe(self.event.event_type, interrupt)
                bus.subscribe(
                    self.event.event_type,
                    lambda event: calls.append("after"),
                )

                with self.assertRaises(type(interruption)) as raised:
                    bus.publish(self.event)

                self.assertIs(raised.exception, interruption)
                self.assertEqual(calls, ["interrupt"])


class CareerEventBusSingletonTest(unittest.TestCase):
    def test_singleton_is_fresh_and_empty_after_harness_reset(self):
        received = []

        with InProcessCareer():
            eventbus = importlib.import_module("eventbus")
            first = eventbus.CareerEventBus()
            self.assertIs(first, eventbus.CareerEventBus())
            first.subscribe("career.commit.initiated", received.append)
            first_instance = first

        with InProcessCareer():
            eventbus = importlib.import_module("eventbus")
            events = importlib.import_module("events")
            second = eventbus.CareerEventBus()
            event = events.CommitInitiated(
                event_id="fresh-event",
                operation_id="fresh-operation",
                occurred_at=datetime(
                    2026,
                    9,
                    19,
                    13,
                    14,
                    7,
                    tzinfo=timezone.utc,
                ),
                head=events.HeadSnapshot(context="", mission="", thread=""),
            )
            second.publish(event)

            self.assertIs(second, eventbus.CareerEventBus())
            self.assertIsNot(second, first_instance)
            self.assertEqual(received, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
