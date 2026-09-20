"""Real-Git CLI tests for merging finished structural scopes."""

import json
import os
import subprocess
import sys
import unittest

from inprocess_harness import InProcessCareer, SOURCE


SCOPE_CASES = (
    (
        "context",
        "snt",
        (),
        "snt",
        "snt/@context",
        "@career",
        {"context": "", "mission": "", "thread": ""},
    ),
    (
        "mission",
        "daedalux",
        (("context", "snt"),),
        "snt/daedalux",
        "snt/daedalux/@mission",
        "snt/@context",
        {"context": "snt", "mission": "", "thread": ""},
    ),
    (
        "thread",
        "debugging",
        (("context", "snt"), ("mission", "daedalux")),
        "snt/daedalux/debugging",
        "snt/daedalux/debugging/@thread",
        "snt/daedalux/@mission",
        {"context": "snt", "mission": "daedalux", "thread": ""},
    ),
)


class FinishMergeTest(unittest.TestCase):
    def cli(
        self,
        career: InProcessCareer,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """@brief Run the real Career CLI and capture its process result."""
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

    def dispatch_ok(self, career: InProcessCareer, *args: str) -> None:
        """@brief Run a Career command and require success."""
        result = career.dispatch(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def git_ok(
        self,
        career: InProcessCareer,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """@brief Run Git and require success."""
        result = career.git(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def initialize_scope(
        self,
        career: InProcessCareer,
        kind: str,
        identifier: str,
        parents: tuple[tuple[str, str], ...],
    ) -> None:
        """@brief Initialize a Career archive at one structural scope."""
        self.dispatch_ok(career, "init")
        for parent_kind, parent_id in parents:
            self.dispatch_ok(career, parent_kind, "start", parent_id)
        self.dispatch_ok(career, kind, "start", identifier)

    def revision(self, career: InProcessCareer, name: str = "HEAD") -> str:
        """@brief Resolve one Git revision to its full object name."""
        return self.git_ok(career, "rev-parse", name).stdout.strip()

    def write_hook(self, career: InProcessCareer, name: str, script: str) -> None:
        """@brief Install one executable Git hook in an isolated archive."""
        hook = career.repo / ".git" / "hooks" / name
        hook.write_bytes(script.encode("utf-8"))
        hook.chmod(0o755)

    def assert_no_merge(self, career: InProcessCareer) -> None:
        """@brief Require that the isolated repository has no MERGE_HEAD."""
        self.assertEqual(
            career.git(
                "rev-parse",
                "--verify",
                "--quiet",
                "MERGE_HEAD",
            ).returncode,
            1,
        )

    def repository_files(self, career: InProcessCareer) -> dict[str, bytes]:
        """@brief Snapshot all non-Git files in the Career archive."""
        return {
            path.relative_to(career.repo).as_posix(): path.read_bytes()
            for path in career.repo.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(career.repo).parts
        }

    def repository_state(self, career: InProcessCareer) -> tuple[object, ...]:
        """@brief Snapshot refs, branch, revision, index, and working tree."""
        refs = self.git_ok(
            career,
            "for-each-ref",
            "--format=%(refname):%(objectname)",
            "refs/heads",
        ).stdout
        return (
            refs,
            self.git_ok(career, "branch", "--show-current").stdout.strip(),
            self.revision(career),
            self.git_ok(career, "write-tree").stdout.strip(),
            self.git_ok(career, "status", "--porcelain=v1", "-uall").stdout,
            self.repository_files(career),
        )

    def test_finish_merges_resources_and_history_for_every_scope(self):
        for kind, identifier, parents, path, branch, parent, expected_head in SCOPE_CASES:
            with self.subTest(kind=kind), InProcessCareer() as career:
                self.initialize_scope(career, kind, identifier, parents)
                source = career.cwd / "evidence.txt"
                contents = f"captured {kind} evidence\n"
                source.write_text(contents, encoding="utf-8")
                self.dispatch_ok(career, "add", source.name)
                self.dispatch_ok(career, "commit", "-m", f"Record {kind} work")
                work_commit = self.revision(career)

                result = self.cli(career, kind, "finish")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(
                    self.git_ok(career, "branch", "--show-current").stdout.strip(),
                    parent,
                )
                self.assertEqual(
                    json.loads(
                        (career.repo / ".career" / "HEAD.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    expected_head,
                )
                self.assertEqual(
                    career.git(
                        "show-ref",
                        "--verify",
                        "--quiet",
                        f"refs/heads/{branch}",
                    ).returncode,
                    1,
                )
                self.assertEqual(
                    career.git(
                        "merge-base",
                        "--is-ancestor",
                        work_commit,
                        parent,
                    ).returncode,
                    0,
                )
                self.git_ok(career, "cat-file", "-e", work_commit)
                self.assertEqual(
                    (career.repo / path / source.name).read_text(encoding="utf-8"),
                    contents,
                )
                self.assertFalse((career.repo / path / ".career").exists())
                self.assertEqual(
                    self.git_ok(
                        career,
                        "show",
                        f"{parent}:{path}/{source.name}",
                    ).stdout,
                    contents,
                )
                self.assertNotEqual(
                    career.git(
                        "cat-file",
                        "-e",
                        f"{parent}:{path}/.career",
                    ).returncode,
                    0,
                )
                self.assertEqual(
                    self.git_ok(career, "status", "--porcelain=v1").stdout,
                    "",
                )
                self.assertEqual(
                    self.git_ok(career, "log", "-1", "--format=%s").stdout.strip(),
                    f"Finish {kind} {identifier}",
                )
                merge_line = self.git_ok(
                    career,
                    "rev-list",
                    "--parents",
                    "-n",
                    "1",
                    "HEAD",
                ).stdout.split()
                self.assertEqual(len(merge_line), 3)

    def test_finished_empty_scope_leaves_no_directory(self):
        for kind, identifier, parents, path, branch, parent, _head in SCOPE_CASES:
            with self.subTest(kind=kind), InProcessCareer() as career:
                self.initialize_scope(career, kind, identifier, parents)
                finished_tip = self.revision(career)

                result = self.cli(career, kind, "finish")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((career.repo / path).exists())
                self.assertEqual(
                    self.git_ok(career, "ls-tree", "HEAD", "--", path).stdout,
                    "",
                )
                self.assertEqual(
                    career.git(
                        "merge-base",
                        "--is-ancestor",
                        finished_tip,
                        parent,
                    ).returncode,
                    0,
                )
                self.assertEqual(
                    career.git(
                        "show-ref",
                        "--verify",
                        "--quiet",
                        f"refs/heads/{branch}",
                    ).returncode,
                    1,
                )
                merge_line = self.git_ok(
                    career,
                    "rev-list",
                    "--parents",
                    "-n",
                    "1",
                    "HEAD",
                ).stdout.split()
                self.assertEqual(len(merge_line), 3)

    def test_unsigned_merge_refusal_restores_original_state_and_error(self):
        with InProcessCareer() as career:
            self.initialize_scope(
                career,
                "thread",
                "debugging",
                (("context", "snt"), ("mission", "daedalux")),
            )
            self.git_ok(career, "config", "merge.verifySignatures", "true")
            before = self.repository_state(career)

            result = self.cli(career, "thread", "finish")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("signature", result.stderr.lower())
            self.assertEqual(self.repository_state(career), before)
            self.assert_no_merge(career)

    def test_staged_changes_are_refused_before_finish_changes_anything(self):
        with InProcessCareer() as career:
            self.initialize_scope(
                career,
                "thread",
                "debugging",
                (("context", "snt"), ("mission", "daedalux")),
            )
            source = career.cwd / "staged.txt"
            source.write_text("not committed\n", encoding="utf-8")
            self.dispatch_ok(career, "add", source.name)
            before = self.repository_state(career)

            result = self.cli(career, "thread", "finish")

            self.assertEqual(result.returncode, 128)
            self.assertTrue(result.stderr.startswith("fatal:"), result.stderr)
            self.assertIn("commit or unstage", result.stderr)
            self.assertEqual(self.repository_state(career), before)
            self.assert_no_merge(career)

    def test_rejected_merge_commit_restores_original_state_and_hook_error(self):
        with InProcessCareer() as career:
            self.initialize_scope(
                career,
                "thread",
                "debugging",
                (("context", "snt"), ("mission", "daedalux")),
            )
            self.write_hook(
                career,
                "pre-commit",
                "#!/bin/sh\n"
                "echo 'finish commit rejected by hook' >&2\n"
                "exit 1\n",
            )
            before = self.repository_state(career)

            result = self.cli(career, "thread", "finish")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("finish commit rejected by hook", result.stderr)
            self.assertEqual(self.repository_state(career), before)
            self.assert_no_merge(career)

    def test_rejected_branch_deletion_restores_parent_and_finished_branch(self):
        with InProcessCareer() as career:
            self.initialize_scope(
                career,
                "thread",
                "debugging",
                (("context", "snt"), ("mission", "daedalux")),
            )
            branch = "snt/daedalux/debugging/@thread"
            self.write_hook(
                career,
                "reference-transaction",
                "#!/bin/sh\n"
                "if [ \"$1\" = \"prepared\" ]; then\n"
                "    while read old new ref; do\n"
                f"        if [ \"$ref\" = \"refs/heads/{branch}\" ]; then\n"
                "            case \"$new\" in\n"
                "                000000*)\n"
                "                    echo 'finish branch deletion rejected by hook' >&2\n"
                "                    exit 1\n"
                "                    ;;\n"
                "            esac\n"
                "        fi\n"
                "    done\n"
                "fi\n"
                "exit 0\n",
            )
            before = self.repository_state(career)

            result = self.cli(career, "thread", "finish")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("finish branch deletion rejected by hook", result.stderr)
            self.assertEqual(self.repository_state(career), before)
            self.assert_no_merge(career)

    def test_merge_conflict_restores_every_scope_without_changes(self):
        for kind, identifier, parents, _path, branch, parent, _head in SCOPE_CASES:
            with self.subTest(kind=kind), InProcessCareer() as career:
                self.dispatch_ok(career, "init")
                for parent_kind, parent_id in parents:
                    self.dispatch_ok(career, parent_kind, "start", parent_id)

                conflict = career.repo / "conflict.txt"
                conflict.write_text("common\n", encoding="utf-8")
                self.git_ok(career, "add", "--", conflict.name)
                self.git_ok(career, "commit", "-m", "Add common resource")

                self.dispatch_ok(career, kind, "start", identifier)
                conflict.write_text("finished scope\n", encoding="utf-8")
                self.git_ok(career, "add", "--", conflict.name)
                self.git_ok(career, "commit", "-m", "Change resource in scope")

                self.git_ok(career, "switch", parent)
                conflict.write_text("structural parent\n", encoding="utf-8")
                self.git_ok(career, "add", "--", conflict.name)
                self.git_ok(career, "commit", "-m", "Change resource in parent")
                self.git_ok(career, "switch", branch)
                before = self.repository_state(career)

                result = self.cli(career, kind, "finish")

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.repository_state(career), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
