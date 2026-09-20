"""Real-Git integration tests for Career archive initialization."""

import json
import os
import subprocess
import sys

from inprocess_harness import InProcessCareerTestCase, SOURCE


class CareerInitTest(InProcessCareerTestCase):
    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        """@brief Run the real Career CLI in the isolated test environment."""
        return subprocess.run(
            [sys.executable, str(SOURCE / "main.py"), *args],
            cwd=self.career.cwd,
            env=os.environ.copy(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            check=False,
        )

    def git_ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        """@brief Run Git and require a successful result."""
        result = self.career.git(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def revision(self) -> str:
        """@brief Return the current full Git revision."""
        return self.git_ok("rev-parse", "HEAD").stdout.strip()

    def commit_count(self) -> int:
        """@brief Return the number of commits reachable from HEAD."""
        return int(self.git_ok("rev-list", "--count", "HEAD").stdout)

    def test_init_creates_one_career_root_commit(self):
        result = self.career.dispatch("init")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.git_ok("branch", "--show-current").stdout.strip(),
            "@career",
        )
        self.assertEqual(self.commit_count(), 1)
        self.assertEqual(
            self.git_ok("log", "-1", "--format=%s").stdout.strip(),
            "Initialize Career archive",
        )
        self.assertEqual(
            json.loads(
                (self.career.repo / ".career" / "HEAD.json").read_text(
                    encoding="utf-8"
                )
            ),
            {"context": "", "mission": "", "thread": ""},
        )
        self.assertEqual(self.git_ok("status", "--porcelain").stdout, "")

    def test_repeated_init_keeps_the_existing_root_commit(self):
        first = self.career.dispatch("init")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        revision = self.revision()

        second = self.career.dispatch("init")

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.revision(), revision)
        self.assertEqual(self.commit_count(), 1)

    def test_init_without_identity_can_be_retried_after_configuration(self):
        identity = {
            name: os.environ.pop(name)
            for name in (
                "GIT_AUTHOR_NAME",
                "GIT_AUTHOR_EMAIL",
                "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL",
            )
        }

        failed = self.cli("init")

        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("Author identity unknown", failed.stderr)
        self.assertNotEqual(
            self.career.git("rev-parse", "--verify", "HEAD").returncode,
            0,
        )

        os.environ.update(identity)
        retried = self.cli("init")

        self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
        self.assertEqual(self.commit_count(), 1)
        self.assertEqual(
            self.git_ok("log", "-1", "--format=%s").stdout.strip(),
            "Initialize Career archive",
        )


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
