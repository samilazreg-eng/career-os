"""Unit tests for the immutable Career event model."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from events import (  # noqa: E402
    SCHEMA_VERSION,
    CareerEvent,
    CommitCompleted,
    CommitInitiated,
    CommitInReview,
    CommitReviewed,
    HeadSnapshot,
)


class CareerEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.occurred_at = datetime(2026, 9, 19, 13, 14, 7, tzinfo=timezone.utc)
        self.head = HeadSnapshot(context="snt", mission="daedalux", thread="")
        self.common = {
            "event_id": "event-1",
            "operation_id": "operation-1",
            "occurred_at": self.occurred_at,
            "head": self.head,
        }

    def test_event_classes_are_frozen(self):
        event = CommitInitiated(**self.common)

        with self.assertRaises(FrozenInstanceError):
            event.operation_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            event.head.context = "changed"

    def test_each_event_serializes_to_json_compatible_dictionary(self):
        events = (
            CommitInitiated(**self.common),
            CommitInReview(**self.common),
            CommitReviewed(**self.common, workspace_revision="a" * 40),
            CommitCompleted(**self.common, workspace_revision="b" * 64),
        )

        for event in events:
            with self.subTest(event_type=event.event_type):
                serialized = event.to_dict()
                self.assertEqual(json.loads(json.dumps(serialized)), serialized)
                self.assertEqual(serialized["schema_version"], "1")

    def test_initiated_dictionary_has_the_exact_versioned_schema(self):
        event = CommitInitiated(**self.common)

        self.assertEqual(
            event.to_dict(),
            {
                "schema_version": "1",
                "event_id": "event-1",
                "operation_id": "operation-1",
                "event_type": "career.commit.initiated",
                "occurred_at": "2026-09-19T13:14:07+00:00",
                "head": {
                    "context": "snt",
                    "mission": "daedalux",
                    "thread": "",
                },
            },
        )

    def test_free_form_payload_fields_are_not_accepted(self):
        for field in ("payload", "file_content", "commit_message"):
            with self.subTest(field=field):
                with self.assertRaises(TypeError):
                    CommitInitiated(**self.common, **{field: "private"})

    def test_serialization_preserves_empty_head_levels(self):
        event = CommitInitiated(
            **self.common | {"head": HeadSnapshot(context="", mission="", thread="")}
        )

        self.assertEqual(
            event.to_dict()["head"],
            {"context": "", "mission": "", "thread": ""},
        )

    def test_utc_timestamp_uses_iso_strict_whole_seconds(self):
        event = CommitInitiated(**self.common)

        self.assertEqual(event.to_dict()["occurred_at"], "2026-09-19T13:14:07+00:00")

    def test_invalid_timestamps_are_rejected(self):
        invalid_values = (
            datetime(2026, 9, 19, 13, 14, 7),
            datetime(
                2026,
                9,
                19,
                14,
                14,
                7,
                tzinfo=timezone(timedelta(hours=1)),
            ),
            datetime(2026, 9, 19, 13, 14, 7, 1, tzinfo=timezone.utc),
        )

        for occurred_at in invalid_values:
            with self.subTest(occurred_at=occurred_at):
                with self.assertRaises(ValueError):
                    CommitInitiated(**self.common | {"occurred_at": occurred_at})

    def test_event_type_is_owned_by_each_class(self):
        expected = {
            CommitInitiated: "career.commit.initiated",
            CommitInReview: "career.commit.in_review",
            CommitReviewed: "career.commit.reviewed",
            CommitCompleted: "career.commit.completed",
        }

        for event_class, event_type in expected.items():
            arguments = self.common.copy()
            if event_class in (CommitReviewed, CommitCompleted):
                arguments["workspace_revision"] = "a" * 40
            event = event_class(**arguments)

            with self.subTest(event_class=event_class.__name__):
                self.assertEqual(event.event_type, event_type)
                self.assertEqual(event.to_dict()["event_type"], event_type)
                with self.assertRaises(TypeError):
                    event_class(**arguments, event_type="career.commit.changed")
                with self.assertRaises(FrozenInstanceError):
                    event.event_type = "career.commit.changed"

    def test_schema_version_is_fixed_and_serialized(self):
        event = CommitInitiated(**self.common)

        self.assertEqual(SCHEMA_VERSION, "1")
        self.assertEqual(event.schema_version, SCHEMA_VERSION)
        self.assertEqual(event.to_dict()["schema_version"], SCHEMA_VERSION)
        with self.assertRaises(TypeError):
            CommitInitiated(**self.common, schema_version="2")

    def test_workspace_revision_exists_only_after_review(self):
        initiated = CommitInitiated(**self.common)
        in_review = CommitInReview(**self.common)
        reviewed = CommitReviewed(**self.common, workspace_revision="a" * 40)
        completed = CommitCompleted(**self.common, workspace_revision="b" * 64)

        self.assertFalse(hasattr(initiated, "workspace_revision"))
        self.assertFalse(hasattr(in_review, "workspace_revision"))
        self.assertEqual(reviewed.workspace_revision, "a" * 40)
        self.assertEqual(completed.workspace_revision, "b" * 64)

    def test_workspace_revision_accepts_full_sha1_and_sha256_names(self):
        for revision in ("0123456789abcdef" * 2 + "01234567", "a" * 64):
            with self.subTest(length=len(revision)):
                event = CommitReviewed(**self.common, workspace_revision=revision)
                self.assertEqual(event.to_dict()["workspace_revision"], revision)

    def test_workspace_revision_rejects_abbreviated_or_non_hex_names(self):
        invalid_revisions = ("a" * 39, "a" * 41, "A" * 40, "g" * 40, "a" * 63)

        for revision in invalid_revisions:
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    CommitReviewed(**self.common, workspace_revision=revision)
                with self.assertRaises(ValueError):
                    CommitCompleted(**self.common, workspace_revision=revision)

    def test_event_classes_share_the_common_base(self):
        for event_class in (
            CommitInitiated,
            CommitInReview,
            CommitReviewed,
            CommitCompleted,
        ):
            self.assertTrue(issubclass(event_class, CareerEvent))

    def test_events_import_without_application_modules_or_harness(self):
        code = (
            "import sys; "
            f"sys.path.insert(0, {str(SOURCE)!r}); "
            "import events; "
            "forbidden = {'paths', 'head', 'git', 'template.singleton'}; "
            "assert forbidden.isdisjoint(sys.modules)"
        )

        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
