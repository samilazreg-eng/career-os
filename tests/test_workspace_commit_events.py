"""Real-Git integration tests for Workspace commit event publication."""

from datetime import datetime, timezone
import importlib
from pathlib import Path
import subprocess
import uuid

from inprocess_harness import InProcessCareerTestCase


EVENT_TYPES = (
    "career.commit.initiated",
    "career.commit.in_review",
    "career.commit.reviewed",
    "career.commit.completed",
)


class WorkspaceCommitEventsTest(InProcessCareerTestCase):
    def setUp(self) -> None:
        super().setUp()
        initialized = self.career.dispatch("init")
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        self.git_ok("commit", "--allow-empty", "-m", "Fixture root")

        self.eventbus = importlib.import_module("eventbus")
        self.error_module = importlib.import_module("error")
        self.git_module = importlib.import_module("git")
        self.workspace_module = importlib.import_module("workspace")
        self.bus = self.eventbus.CareerEventBus()

    def git_ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = self.career.git(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def head_revision(self) -> str:
        return self.git_ok("rev-parse", "HEAD").stdout.strip()

    def stage(self, name: str, content: str = "content\n") -> Path:
        path = self.career.repo / name
        path.write_text(content, encoding="utf-8")
        self.git_ok("add", "--", name)
        return path

    def subscribe_all(self, handler) -> None:
        for event_type in EVENT_TYPES:
            self.bus.subscribe(event_type, handler)

    def test_successful_commit_publishes_ordered_correlated_events(self):
        observations = []

        def record(event):
            observations.append((event, self.head_revision()))

        self.subscribe_all(record)
        old_revision = self.head_revision()
        self.stage("resource.txt")
        earliest = datetime.now(timezone.utc).replace(microsecond=0)

        result = self.career.dispatch("commit", "-m", "Record resource")

        latest = datetime.now(timezone.utc).replace(microsecond=0)
        new_revision = self.head_revision()
        published = [event for event, revision in observations]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([event.event_type for event in published], list(EVENT_TYPES))
        self.assertEqual(len({event.operation_id for event in published}), 1)
        self.assertEqual(str(uuid.UUID(published[0].operation_id)), published[0].operation_id)
        self.assertEqual(len({event.event_id for event in published}), 4)
        for event in published:
            self.assertEqual(str(uuid.UUID(event.event_id)), event.event_id)
            self.assertEqual(event.occurred_at.tzinfo, timezone.utc)
            self.assertEqual(event.occurred_at.microsecond, 0)
            self.assertLessEqual(earliest, event.occurred_at)
            self.assertLessEqual(event.occurred_at, latest)
        self.assertEqual(
            [event.occurred_at for event in published],
            sorted(event.occurred_at for event in published),
        )
        self.assertEqual([revision for event, revision in observations[:2]], [old_revision] * 2)
        self.assertEqual([revision for event, revision in observations[2:]], [new_revision] * 2)
        self.assertNotEqual(new_revision, old_revision)
        self.assertEqual(len(new_revision), 40)
        self.assertEqual(observations[2][0].workspace_revision, new_revision)
        self.assertEqual(observations[3][0].workspace_revision, new_revision)
        self.assertEqual(self.git_ok("status", "--porcelain").stdout, "")

    def test_events_copy_every_current_head_depth(self):
        recorded = []
        self.subscribe_all(recorded.append)
        workspace = self.career.main.Career().workspace
        states = (
            ("", "", ""),
            ("snt", "", ""),
            ("snt", "daedalux", ""),
            ("snt", "daedalux", "debugging"),
        )

        for index, (context, mission, thread) in enumerate(states):
            workspace.head.set_context(context)
            workspace.head.set_mission(mission)
            workspace.head.set_thread(thread)
            self.stage(f"resource-{index}.txt")

            result = self.career.dispatch("commit", "-m", f"Snapshot {index}")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            group = recorded[index * 4:(index + 1) * 4]
            self.assertEqual(len(group), 4)
            for event in group:
                self.assertEqual(
                    (event.head.context, event.head.mission, event.head.thread),
                    (context, mission, thread),
                )

        for index, state in enumerate(states):
            for event in recorded[index * 4:(index + 1) * 4]:
                self.assertEqual(
                    (event.head.context, event.head.mission, event.head.thread),
                    state,
                )

    def test_clean_commit_preserves_result_and_publishes_nothing(self):
        recorded = []
        self.subscribe_all(recorded.append)

        result = self.career.dispatch("commit", "-m", "Nothing staged")

        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing to commit", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(recorded, [])

    def test_unstaged_and_untracked_changes_publish_nothing(self):
        tracked = self.career.repo / "tracked.txt"
        tracked.write_text("before\n", encoding="utf-8")
        self.git_ok("add", "--", tracked.name)
        self.git_ok("commit", "-m", "Track resource")
        tracked.write_text("unstaged\n", encoding="utf-8")
        (self.career.repo / "untracked.txt").write_text(
            "untracked\n",
            encoding="utf-8",
        )
        recorded = []
        self.subscribe_all(recorded.append)

        result = self.career.dispatch("commit", "-m", "Nothing staged")

        self.assertEqual(result.returncode, 1)
        self.assertIn("no changes added to commit", result.stdout)
        self.assertEqual(recorded, [])

    def test_race_to_no_staged_changes_stops_after_review_started(self):
        recorded = []
        self.subscribe_all(recorded.append)
        self.stage("raced.txt")

        def unstage(event):
            self.git_ok("reset", "HEAD", "--", "raced.txt")

        self.bus.subscribe("career.commit.initiated", unstage)

        result = self.career.dispatch("commit", "-m", "Raced commit")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            [event.event_type for event in recorded],
            ["career.commit.initiated", "career.commit.in_review"],
        )

    def test_git_failure_stops_before_reviewed_and_drops_delivery_errors(self):
        recorded = []
        self.subscribe_all(recorded.append)
        self.stage("locked.txt")

        def fail_delivery(event):
            raise ValueError("delivery failed before Git")

        self.bus.subscribe("career.commit.initiated", fail_delivery)
        (self.career.repo / ".git" / "index.lock").write_text("locked", encoding="utf-8")

        with self.assertRaises(self.git_module.GitError):
            self.career.dispatch("commit", "-m", "Cannot commit")

        self.assertEqual(
            [event.event_type for event in recorded],
            ["career.commit.initiated", "career.commit.in_review"],
        )

    def test_delivery_failures_are_aggregated_after_successful_commit(self):
        recorded = []
        self.subscribe_all(recorded.append)
        failures = {
            "career.commit.initiated": ValueError("initiated failed"),
            "career.commit.in_review": RuntimeError("review failed"),
            "career.commit.completed": LookupError("completed failed"),
        }

        for event_type, failure in failures.items():
            def fail(event, failure=failure):
                raise failure

            self.bus.subscribe(event_type, fail)

        self.stage("committed.txt")

        with self.assertRaises(self.workspace_module.CommitEventsError) as raised:
            self.career.dispatch("commit", "-m", "Commit despite delivery")

        self.assertEqual(raised.exception.result.returncode, 0)
        self.assertIsInstance(raised.exception, RuntimeError)
        self.assertNotIsInstance(raised.exception, self.error_module.CareerError)
        self.assertEqual(len(raised.exception.errors), 3)
        self.assertEqual(
            [error.event.event_type for error in raised.exception.errors],
            list(failures),
        )
        self.assertEqual([event.event_type for event in recorded], list(EVENT_TYPES))
        self.assertEqual(
            self.git_ok("log", "-1", "--format=%B").stdout.strip(),
            "Commit despite delivery",
        )

    def test_reviewed_failure_prevents_completed_but_keeps_commit(self):
        recorded = []
        self.subscribe_all(recorded.append)

        def fail_reviewed(event):
            raise ValueError("knowledge update failed")

        self.bus.subscribe("career.commit.reviewed", fail_reviewed)
        self.stage("reviewed.txt")

        with self.assertRaises(self.workspace_module.CommitEventsError) as raised:
            self.career.dispatch("commit", "-m", "Reviewed failure")

        self.assertEqual(raised.exception.result.returncode, 0)
        self.assertEqual(len(raised.exception.errors), 1)
        self.assertEqual(
            [event.event_type for event in recorded],
            list(EVENT_TYPES[:3]),
        )
        self.assertEqual(self.git_ok("log", "-1", "--format=%B").stdout.strip(), "Reviewed failure")

    def test_structural_start_and_finish_commands_publish_nothing(self):
        recorded = []
        self.subscribe_all(recorded.append)

        for args in (
            ("context", "start", "snt"),
            ("mission", "start", "daedalux"),
            ("thread", "start", "debugging"),
        ):
            result = self.career.dispatch(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        lifecycle = (
            (
                "snt/daedalux/@mission",
                "snt/daedalux/debugging/@thread",
                ("thread", "finish"),
            ),
            (
                "snt/@context",
                "snt/daedalux/@mission",
                ("mission", "finish"),
            ),
            (
                "@career",
                "snt/@context",
                ("context", "finish"),
            ),
        )
        for parent, child, command in lifecycle:
            self.git_ok("switch", parent)
            self.git_ok("merge", "--ff-only", child)
            self.git_ok("switch", child)
            result = self.career.dispatch(*command)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        self.assertEqual(recorded, [])


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
