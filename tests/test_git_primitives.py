"""Real-Git tests for revision and staged-change read primitives."""

import importlib
from pathlib import Path
import subprocess

from inprocess_harness import InProcessCareerTestCase


class GitInitializationPrimitivesTest(InProcessCareerTestCase):
    def test_empty_commit_creates_head_in_an_unborn_repository(self):
        self.career.repo.mkdir()
        initialized = self.career.git("init", "-b", "@career")
        self.assertEqual(
            initialized.returncode,
            0,
            initialized.stdout + initialized.stderr,
        )
        git_module = importlib.import_module("git")
        git = git_module.Git()

        self.assertFalse(git.has_head())

        committed = git.commit_empty("Generic empty commit")

        self.assertEqual(
            committed.returncode,
            0,
            committed.stdout + committed.stderr,
        )
        self.assertTrue(git.has_head())
        self.assertEqual(
            self.career.git("log", "-1", "--format=%s").stdout.strip(),
            "Generic empty commit",
        )


class GitPrimitivesTest(InProcessCareerTestCase):
    def setUp(self) -> None:
        super().setUp()
        initialized = self.career.dispatch("init")
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        self.git_module = importlib.import_module("git")
        self.repository_module = importlib.import_module("repository")
        self.git = self.git_module.Git()
        self.repository = self.repository_module.Repository()

    def assert_git_ok(
        self,
        result: subprocess.CompletedProcess[str],
    ) -> subprocess.CompletedProcess[str]:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def commit(self, message: str, allow_empty: bool = False) -> str:
        arguments = ["commit"]
        if allow_empty:
            arguments.append("--allow-empty")
        arguments.extend(("-m", message))
        self.assert_git_ok(self.career.git(*arguments))
        return self.assert_git_ok(self.career.git("rev-parse", "HEAD")).stdout.strip()

    def stage(self, path: Path) -> None:
        self.assert_git_ok(self.career.git("add", "--", str(path.relative_to(self.career.repo))))

    def remove_head(self) -> None:
        """@brief Restore an unborn ``@career`` branch for primitive tests."""
        self.assert_git_ok(
            self.career.git("update-ref", "-d", "refs/heads/@career")
        )

    def test_staged_changes_on_unborn_and_clean_repositories(self):
        self.remove_head()
        self.assertFalse(self.git.has_staged_changes())

        resource = self.career.repo / "new.txt"
        resource.write_text("new\n", encoding="utf-8")
        self.stage(resource)
        self.assertTrue(self.git.has_staged_changes())

        self.commit("Track new file")
        self.assertFalse(self.git.has_staged_changes())

    def test_staged_modification_is_detected(self):
        resource = self.career.repo / "tracked.txt"
        resource.write_text("before\n", encoding="utf-8")
        self.stage(resource)
        self.commit("Track resource")

        resource.write_text("after\n", encoding="utf-8")
        self.stage(resource)

        self.assertTrue(self.git.has_staged_changes())

    def test_staged_deletion_is_detected(self):
        resource = self.career.repo / "tracked.txt"
        resource.write_text("tracked\n", encoding="utf-8")
        self.stage(resource)
        self.commit("Track resource")

        resource.unlink()
        self.stage(resource)

        self.assertTrue(self.git.has_staged_changes())

    def test_unstaged_modification_is_not_reported_as_staged(self):
        resource = self.career.repo / "tracked.txt"
        resource.write_text("before\n", encoding="utf-8")
        self.stage(resource)
        self.commit("Track resource")

        resource.write_text("after\n", encoding="utf-8")

        self.assertFalse(self.git.has_staged_changes())
        self.assertFalse(self.repository.has_staged_changes())

    def test_untracked_file_is_not_reported_as_staged(self):
        untracked = self.career.repo / "untracked.txt"
        untracked.write_text("untracked\n", encoding="utf-8")

        self.assertFalse(self.git.has_staged_changes())
        self.assertFalse(self.repository.has_staged_changes())

    def test_staged_change_wins_only_while_it_remains_staged(self):
        tracked = self.career.repo / "tracked.txt"
        tracked.write_text("before\n", encoding="utf-8")
        self.stage(tracked)
        self.commit("Track resource")

        tracked.write_text("unstaged modification\n", encoding="utf-8")
        untracked = self.career.repo / "untracked.txt"
        untracked.write_text("untracked\n", encoding="utf-8")
        staged = self.career.repo / "staged.txt"
        staged.write_text("staged\n", encoding="utf-8")
        self.stage(staged)

        self.assertTrue(self.git.has_staged_changes())
        self.assertTrue(self.repository.has_staged_changes())

        self.commit("Commit staged resource")

        self.assertFalse(self.git.has_staged_changes())
        self.assertFalse(self.repository.has_staged_changes())

    def test_head_revision_matches_git_and_changes_after_commit(self):
        first = self.commit("First", allow_empty=True)

        self.assertEqual(len(first), 40)
        self.assertEqual(self.git.head_revision(), first)

        second = self.commit("Second", allow_empty=True)

        self.assertNotEqual(second, first)
        self.assertEqual(self.git.head_revision(), second)

    def test_head_revision_raises_on_repository_without_commit(self):
        self.remove_head()
        with self.assertRaises(self.git_module.GitError) as raised:
            self.git.head_revision()

        self.assertNotEqual(raised.exception.result.returncode, 0)

    def test_unexpected_staged_changes_exit_code_raises_git_error(self):
        self.commit("Root", allow_empty=True)
        index = self.career.repo / ".git" / "index"
        index.write_bytes(b"invalid index")

        with self.assertRaises(self.git_module.GitError) as raised:
            self.git.has_staged_changes()

        self.assertNotIn(raised.exception.result.returncode, (0, 1))

    def test_repository_passes_through_git_values(self):
        revision = self.commit("Root", allow_empty=True)

        self.assertEqual(self.repository.head_revision(), revision)
        self.assertEqual(self.repository.head_revision(), self.git.head_revision())
        self.assertFalse(self.repository.has_staged_changes())

        resource = self.career.repo / "staged.txt"
        resource.write_text("staged\n", encoding="utf-8")
        self.stage(resource)

        self.assertTrue(self.repository.has_staged_changes())
        self.assertEqual(
            self.repository.has_staged_changes(),
            self.git.has_staged_changes(),
        )


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
