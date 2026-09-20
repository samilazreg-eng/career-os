"""Real-Git tests for structural parent branch creation."""

import subprocess

from inprocess_harness import InProcessCareerTestCase


class StructuralParentTest(InProcessCareerTestCase):
    def setUp(self) -> None:
        super().setUp()
        initialized = self.career.dispatch("init")
        self.assertEqual(
            initialized.returncode,
            0,
            initialized.stdout + initialized.stderr,
        )
        self.start("context", "snt")
        self.start("mission", "daedalux")
        self.start("thread", "debugging")

    def git_ok(self, *args: str) -> subprocess.CompletedProcess[str]:
        """@brief Run Git and require a successful result."""
        result = self.career.git(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def start(self, kind: str, name: str) -> None:
        """@brief Start one structural scope through the Career CLI."""
        result = self.career.dispatch(kind, "start", name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def revision(self, name: str) -> str:
        """@brief Return the full revision for one Git revision expression."""
        return self.git_ok("rev-parse", name).stdout.strip()

    def test_sibling_mission_branches_from_context(self):
        parent = self.revision("snt/@context")

        self.start("mission", "research")

        self.assertEqual(self.revision("HEAD~1"), parent)
        self.assertEqual(
            self.git_ok("branch", "--show-current").stdout.strip(),
            "snt/research/@mission",
        )

    def test_sibling_context_branches_from_career_root(self):
        parent = self.revision("@career")

        self.start("context", "visteon")

        self.assertEqual(self.revision("HEAD~1"), parent)
        self.assertEqual(
            self.git_ok("branch", "--show-current").stdout.strip(),
            "visteon/@context",
        )

    def test_new_context_tree_excludes_the_previous_context(self):
        self.start("context", "visteon")

        tree = self.git_ok(
            "ls-tree",
            "-r",
            "--name-only",
            "visteon/@context",
        ).stdout.splitlines()

        self.assertEqual(tree, ["visteon/.career"])


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
