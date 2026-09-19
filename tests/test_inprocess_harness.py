"""Tests for the isolated in-process Career OS test harness."""

import os
from pathlib import Path
import sys
import unittest

from inprocess_harness import InProcessCareer, InProcessCareerTestCase


def source_snapshot(source: Path) -> dict[Path, tuple[int, int]]:
    """
    @brief Capture file metadata for a source tree.

    @param source Source tree root.

    @return Relative paths mapped to their size and modification time.
    """
    return {
        path.relative_to(source): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in source.rglob("*")
        if path.is_file()
    }


class InProcessCareerHarnessTest(unittest.TestCase):
    def test_consecutive_harnesses_isolate_repository_head_and_singletons(self):
        with InProcessCareer() as first:
            self.assertEqual(first.dispatch("init").returncode, 0)
            first_head = first.main.Career().workspace.head
            first_repository = first.main.Career().repo
            first_head.set_context("first")
            first_repo_dir = first.paths.REPO_DIR

        with InProcessCareer() as second:
            self.assertEqual(second.dispatch("init").returncode, 0)
            second_head = second.main.Career().workspace.head
            second_repository = second.main.Career().repo

            self.assertNotEqual(second.paths.REPO_DIR, first_repo_dir)
            self.assertEqual(second_head.context, "")
            self.assertIsNot(second_head, first_head)
            self.assertIsNot(second_repository, first_repository)

    def test_dispatch_captures_stdout_stderr_and_exit_code(self):
        with InProcessCareer() as career:
            result = career.dispatch("init")

            self.assertEqual(result.returncode, 0)
            self.assertIn("Initialized empty Git repository", result.stdout)
            self.assertEqual(result.stderr, "")

            result = career.dispatch("unknown")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("is not a career command", result.stderr)

    def test_context_restores_process_state_and_removes_fresh_modules(self):
        original_environment = os.environ.copy()
        original_path = sys.path.copy()
        original_modules = sys.modules.copy()
        original_cwd = Path.cwd()

        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            with InProcessCareer() as career:
                fresh_main = career.main
                os.environ["HARNESS_SENTINEL"] = "changed"
                sys.path.append("harness-sentinel")
                raise RuntimeError("fixture failure")

        self.assertEqual(os.environ, original_environment)
        self.assertEqual(sys.path, original_path)
        self.assertEqual(Path.cwd(), original_cwd)
        self.assertEqual(sys.modules, original_modules)
        self.assertNotIn(fresh_main, sys.modules.values())

    def test_existing_singleton_registry_is_restored(self):
        original_path = sys.path.copy()
        original_modules = sys.modules.copy()
        original_bytecode_setting = sys.dont_write_bytecode
        source = Path(__file__).resolve().parents[1] / "src"

        try:
            sys.dont_write_bytecode = True
            sys.path.insert(0, str(source))
            from template.singleton import Singleton

            sys.dont_write_bytecode = original_bytecode_setting

            class Probe(metaclass=Singleton):
                pass

            original_instance = Probe()

            with InProcessCareer():
                self.assertEqual(Singleton._instances, {})

            self.assertIs(Probe(), original_instance)
        finally:
            sys.dont_write_bytecode = original_bytecode_setting
            sys.path[:] = original_path
            for name in tuple(sys.modules):
                if name not in original_modules:
                    sys.modules.pop(name, None)
            sys.modules.update(original_modules)

    def test_files_are_confined_to_temporary_directory(self):
        with InProcessCareer() as career:
            temporary_root = career.base
            repo = career.repo
            cwd = career.cwd
            self.assertEqual(career.dispatch("init").returncode, 0)

            source = cwd / "resource.txt"
            source.write_text("isolated", encoding="utf-8")
            self.assertEqual(career.dispatch("add", source.name).returncode, 0)

            self.assertTrue(repo.is_relative_to(temporary_root))
            self.assertTrue(source.is_relative_to(temporary_root))
            self.assertTrue((repo / source.name).is_file())
            self.assertEqual(os.environ["CAREER_REPO_DIR"], str(repo))
            self.assertEqual(os.environ["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(os.environ["GIT_CONFIG_NOSYSTEM"], "1")

        self.assertFalse(temporary_root.exists())

    def test_runtime_bytecode_writes_are_disabled_and_restored(self):
        source = Path(__file__).resolve().parents[1] / "src"
        before = source_snapshot(source)
        original_setting = sys.dont_write_bytecode

        try:
            sys.dont_write_bytecode = False
            with InProcessCareer() as career:
                self.assertTrue(sys.dont_write_bytecode)
                self.assertEqual(career.dispatch("init").returncode, 0)

            self.assertFalse(sys.dont_write_bytecode)
            self.assertEqual(source_snapshot(source), before)
        finally:
            sys.dont_write_bytecode = original_setting


class InProcessCareerTestCaseTest(InProcessCareerTestCase):
    def test_base_class_provides_a_fresh_fixture(self):
        result = self.career.dispatch("init")

        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.career.repo.is_relative_to(self.career.base))


if __name__ == "__main__":
    unittest.main(verbosity=2)
