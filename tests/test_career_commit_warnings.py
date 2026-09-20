"""In-process CLI tests for non-fatal commit event-delivery warnings."""

import importlib
from pathlib import Path
import subprocess

from inprocess_harness import InProcessCareerTestCase


EVENT_TYPES = (
    "career.commit.initiated",
    "career.commit.in_review",
    "career.commit.reviewed",
    "career.commit.completed",
)


class CareerCommitWarningsTest(InProcessCareerTestCase):
    def setUp(self) -> None:
        super().setUp()
        initialized = self.career.dispatch("init")
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        self.git_ok("commit", "--allow-empty", "-m", "Fixture root")

        self.career_module = importlib.import_module("career")
        self.eventbus = importlib.import_module("eventbus")
        self.bus = self.eventbus.CareerEventBus()

    def git_ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = self.career.git(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def stage(self, name: str, content: str = "content\n") -> Path:
        path = self.career.repo / name
        path.write_text(content, encoding="utf-8")
        self.git_ok("add", "--", name)
        return path

    def subscribe_all(self, handler) -> None:
        for event_type in EVENT_TYPES:
            self.bus.subscribe(event_type, handler)

    def assert_single_failure_warning(
        self,
        event_type: str,
        failure: Exception,
        expected_events: tuple[str, ...] = EVENT_TYPES,
    ) -> None:
        recorded = []
        self.subscribe_all(recorded.append)

        def fail(event):
            raise failure

        self.bus.subscribe(event_type, fail)
        self.stage(f"{event_type.rsplit('.', 1)[-1]}.txt")

        result = self.career.dispatch("commit", "-m", f"Fail {event_type}")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"Fail {event_type}", result.stdout)
        self.assertEqual(
            result.stderr,
            f"warning: event delivery failed ({event_type}): "
            f"{type(failure).__name__}: {str(failure)!r}\n",
        )
        self.assertEqual(
            [event.event_type for event in recorded],
            list(expected_events),
        )
        self.assertEqual(
            self.git_ok("log", "-1", "--format=%B").stdout.strip(),
            f"Fail {event_type}",
        )

    def assert_cli_message_rendering(
        self,
        message: str,
        rendered_message: str,
    ) -> None:
        failure = ValueError(message)

        def fail(event):
            raise failure

        self.bus.subscribe("career.commit.initiated", fail)
        self.stage("escaped-message.txt")

        result = self.career.dispatch("commit", "-m", "Escape warning message")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr.count("\n"), 1)
        self.assertEqual(
            result.stderr,
            "warning: event delivery failed (career.commit.initiated): "
            f"ValueError: {rendered_message}\n",
        )
        self.assertEqual(str(failure), message)

    def test_initiated_failure_warns_and_keeps_successful_commit(self):
        self.assert_single_failure_warning(
            "career.commit.initiated",
            ValueError("suggestion service failed"),
        )

    def test_in_review_failure_warns_and_keeps_successful_commit(self):
        self.assert_single_failure_warning(
            "career.commit.in_review",
            RuntimeError("review service failed"),
        )

    def test_reviewed_failure_warns_and_prevents_completed(self):
        self.assert_single_failure_warning(
            "career.commit.reviewed",
            LookupError("knowledge service failed"),
            EVENT_TYPES[:3],
        )

    def test_multiple_failures_warn_in_call_order_and_remain_inspectable(self):
        first = ValueError("first suggestion failed")
        second = RuntimeError("second suggestion failed")
        third = LookupError("completion observer failed")

        def fail_with(failure):
            def fail(event):
                raise failure

            return fail

        self.bus.subscribe("career.commit.initiated", fail_with(first))
        self.bus.subscribe("career.commit.initiated", fail_with(second))
        self.bus.subscribe("career.commit.completed", fail_with(third))
        self.stage("multiple.txt")
        career = self.career.main.Career()

        result = career.commit("Multiple delivery failures")

        self.assertIsInstance(result, self.career_module.CommitProcess)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stderr,
            "warning: event delivery failed (career.commit.initiated): "
            "ValueError: 'first suggestion failed'\n"
            "warning: event delivery failed (career.commit.initiated): "
            "RuntimeError: 'second suggestion failed'\n"
            "warning: event delivery failed (career.commit.completed): "
            "LookupError: 'completion observer failed'\n",
        )
        self.assertEqual(len(result.errors), 2)
        self.assertEqual(
            [failure for _, failure in result.errors[0].failures],
            [first, second],
        )
        self.assertEqual(
            [failure for _, failure in result.errors[1].failures],
            [third],
        )
        self.assertIs(result.errors[0].__cause__, first)
        self.assertIs(result.errors[1].__cause__, third)

    def test_plain_git_result_is_unchanged_without_failing_subscriber(self):
        career = self.career.main.Career()
        self.stage("without-subscriber.txt")

        without_subscriber = career.commit("Without subscriber")

        self.assertIs(type(without_subscriber), subprocess.CompletedProcess)
        self.assertEqual(without_subscriber.returncode, 0)
        self.assertEqual(without_subscriber.stderr, "")

        self.subscribe_all(lambda event: None)
        self.stage("successful-subscriber.txt")

        successful_subscriber = career.commit("Successful subscriber")

        self.assertIs(type(successful_subscriber), subprocess.CompletedProcess)
        self.assertEqual(successful_subscriber.returncode, 0)
        self.assertEqual(successful_subscriber.stderr, "")

    def test_git_stderr_is_preserved_before_warning_with_newline_separator(self):
        failure = ValueError("delivery failed")

        def fail(event):
            raise failure

        self.bus.subscribe("career.commit.initiated", fail)
        self.stage("git-stderr.txt")
        career = self.career.main.Career()
        original_commit = career.workspace.repo.commit
        native_results = []

        def commit_with_stderr(message: str) -> subprocess.CompletedProcess[str]:
            result = original_commit(message)
            native_result = subprocess.CompletedProcess(
                result.args,
                result.returncode,
                result.stdout,
                "Git diagnostic without newline",
            )
            native_results.append(native_result)
            return native_result

        career.workspace.repo.commit = commit_with_stderr

        result = career.commit("Preserve Git stderr")

        self.assertEqual(result.args, native_results[0].args)
        self.assertEqual(result.returncode, native_results[0].returncode)
        self.assertEqual(result.stdout, native_results[0].stdout)
        self.assertEqual(
            result.stderr,
            "Git diagnostic without newline\n"
            "warning: event delivery failed (career.commit.initiated): "
            "ValueError: 'delivery failed'\n",
        )

    def test_existing_git_stderr_newline_is_not_duplicated(self):
        def fail(event):
            raise ValueError("delivery failed")

        self.bus.subscribe("career.commit.initiated", fail)
        self.stage("git-stderr-newline.txt")
        career = self.career.main.Career()
        original_commit = career.workspace.repo.commit

        def commit_with_stderr(message: str) -> subprocess.CompletedProcess[str]:
            result = original_commit(message)
            return subprocess.CompletedProcess(
                result.args,
                result.returncode,
                result.stdout,
                "Git diagnostic with newline\n",
            )

        career.workspace.repo.commit = commit_with_stderr

        result = career.commit("Preserve Git stderr newline")

        self.assertEqual(
            result.stderr,
            "Git diagnostic with newline\n"
            "warning: event delivery failed (career.commit.initiated): "
            "ValueError: 'delivery failed'\n",
        )

    def test_nonzero_git_result_and_warning_are_both_preserved(self):
        raced = self.stage("raced.txt")

        def unstage(event):
            self.git_ok("reset", "HEAD", "--", raced.name)
            raced.unlink()

        def fail(event):
            raise RuntimeError("review failed after race")

        self.bus.subscribe("career.commit.initiated", unstage)
        self.bus.subscribe("career.commit.in_review", fail)

        result = self.career.dispatch("commit", "-m", "Raced commit")

        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing to commit", result.stdout)
        self.assertEqual(
            result.stderr,
            "warning: event delivery failed (career.commit.in_review): "
            "RuntimeError: 'review failed after race'\n",
        )

    def test_lf_in_handler_message_is_escaped(self):
        self.assert_cli_message_rendering(
            "first\nsecond",
            "'first\\nsecond'",
        )

    def test_cr_in_handler_message_is_escaped(self):
        self.assert_cli_message_rendering(
            "first\rsecond",
            "'first\\rsecond'",
        )

    def test_crlf_in_handler_message_is_escaped(self):
        self.assert_cli_message_rendering(
            "first\r\nsecond",
            "'first\\r\\nsecond'",
        )

    def test_ansi_control_in_handler_message_is_escaped(self):
        self.assert_cli_message_rendering(
            "erase \x1b[2Kdone",
            "'erase \\x1b[2Kdone'",
        )

    def test_unicode_line_separator_in_handler_message_is_escaped(self):
        self.assert_cli_message_rendering(
            "first\u2028second",
            "'first\\u2028second'",
        )

    def test_accented_handler_message_characters_remain_unchanged(self):
        self.assert_cli_message_rendering(
            "échec déjà",
            "'échec déjà'",
        )

    def test_empty_handler_message_is_shown_as_quoted_empty_string(self):
        self.assert_cli_message_rendering("", "''")

    def test_git_stderr_control_characters_are_not_escaped(self):
        failure = ValueError("handler\nfailed")

        def fail(event):
            raise failure

        self.bus.subscribe("career.commit.initiated", fail)
        self.stage("raw-git-stderr.txt")
        career = self.career.main.Career()
        original_commit = career.workspace.repo.commit

        def commit_with_stderr(message: str) -> subprocess.CompletedProcess[str]:
            result = original_commit(message)
            return subprocess.CompletedProcess(
                result.args,
                result.returncode,
                result.stdout,
                "Git\tstderr\x1b[2K\n",
            )

        career.workspace.repo.commit = commit_with_stderr

        result = self.career.dispatch("commit", "-m", "Keep Git stderr raw")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stderr,
            "Git\tstderr\x1b[2K\n"
            "warning: event delivery failed (career.commit.initiated): "
            "ValueError: 'handler\\nfailed'\n",
        )
        self.assertEqual(str(failure), "handler\nfailed")


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
