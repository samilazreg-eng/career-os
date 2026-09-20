"""Real-Git CLI tests for Head and branch consistency checks."""

import json
import os
import subprocess
import sys
import unittest

from inprocess_harness import InProcessCareer, SOURCE


WRITE_COMMANDS = (
    ("add", "payload.txt"),
    ("commit", "-m", "Record work"),
    ("context", "start", "new-context"),
    ("context", "switch", "target-context"),
    ("context", "finish"),
    ("mission", "start", "new-mission"),
    ("mission", "switch", "target-mission"),
    ("mission", "finish"),
    ("thread", "start", "new-thread"),
    ("thread", "switch", "target-thread"),
    ("thread", "finish"),
)


class HeadConsistencyTest(unittest.TestCase):
    def cli(
        self,
        career: InProcessCareer,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """@brief Run the real Career CLI in an isolated environment."""
        return subprocess.run(
            [sys.executable, str(SOURCE / "main.py"), *args],
            cwd=career.cwd,
            env=os.environ.copy(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            check=False,
        )

    def git_ok(
        self,
        career: InProcessCareer,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """@brief Run Git and require a successful result."""
        result = career.git(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def initialize(self, career: InProcessCareer) -> None:
        """@brief Initialize an isolated Career archive."""
        result = self.cli(career, "init")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_head(
        self,
        career: InProcessCareer,
        context: str = "",
        mission: str = "",
        thread: str = "",
    ) -> None:
        """@brief Replace the isolated Career Head state."""
        (career.repo / ".career" / "HEAD.json").write_text(
            json.dumps(
                {
                    "context": context,
                    "mission": mission,
                    "thread": thread,
                }
            ),
            encoding="utf-8",
        )

    def repository_files(self, career: InProcessCareer) -> dict[str, bytes]:
        """@brief Snapshot non-Git files in the Career working tree."""
        files: dict[str, bytes] = {}
        for path in career.repo.rglob("*"):
            relative = path.relative_to(career.repo)
            if path.is_file() and ".git" not in relative.parts:
                files[relative.as_posix()] = path.read_bytes()

        return files

    def repository_state(
        self,
        career: InProcessCareer,
    ) -> tuple[str, str, str, dict[str, bytes]]:
        """@brief Snapshot branch, revision, index, and working-tree state."""
        return (
            self.git_ok(career, "branch", "--show-current").stdout.strip(),
            self.git_ok(career, "rev-parse", "HEAD").stdout.strip(),
            self.git_ok(career, "write-tree").stdout.strip(),
            self.repository_files(career),
        )

    def test_every_write_command_rejects_an_inconsistent_head_without_changes(self):
        for command in WRITE_COMMANDS:
            with self.subTest(command=command), InProcessCareer() as career:
                self.initialize(career)
                (career.cwd / "payload.txt").write_text(
                    "payload\n",
                    encoding="utf-8",
                )
                self.write_head(career, context="ghost")
                before = self.repository_state(career)

                result = self.cli(career, *command)

                self.assertEqual(result.returncode, 128)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("fatal:"), result.stderr)
                self.assertIn("ghost/@context", result.stderr)
                self.assertIn("@career", result.stderr)
                self.assertEqual(self.repository_state(career), before)

    def test_status_and_diff_work_with_an_inconsistent_head(self):
        with InProcessCareer() as career:
            self.initialize(career)
            self.write_head(career, context="ghost")
            before = self.repository_state(career)

            status = self.cli(career, "status")
            diff = self.cli(career, "diff")

            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertEqual(diff.returncode, 0, diff.stdout + diff.stderr)
            self.assertEqual(self.repository_state(career), before)

    def test_detached_head_is_inconsistent_for_write_commands(self):
        with InProcessCareer() as career:
            self.initialize(career)
            self.git_ok(career, "switch", "--detach")
            before = self.repository_state(career)

            result = self.cli(career, "commit", "-m", "Detached")

            self.assertEqual(result.returncode, 128)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr.startswith("fatal:"), result.stderr)
            self.assertIn("@career", result.stderr)
            self.assertIn("<detached HEAD>", result.stderr)
            self.assertEqual(self.repository_state(career), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
