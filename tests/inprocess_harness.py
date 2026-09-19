"""Fresh in-process Career OS fixtures for integration tests."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import importlib
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import ModuleType
from typing import Self


SOURCE = Path(__file__).resolve().parents[1] / "src"


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """@brief Captured result of one ``main.dispatch`` call."""

    returncode: int
    stdout: str
    stderr: str


def _module_is_from_source(module: ModuleType) -> bool:
    """
    @brief Determine whether a module was loaded from the production source.

    @param module Imported module to inspect.

    @return True when a module file or package path is rooted in ``src``.
    """
    locations: list[str] = []
    filename = getattr(module, "__file__", None)
    if filename:
        locations.append(filename)

    module_path = getattr(module, "__path__", ()) or ()
    locations.extend(str(location) for location in module_path)

    for location in locations:
        try:
            if Path(location).resolve().is_relative_to(SOURCE):
                return True
        except (OSError, RuntimeError, ValueError):
            continue

    return False


def _source_modules() -> list[ModuleType]:
    """
    @brief Find all currently loaded production modules.

    @return Modules whose file or package path is rooted in ``src``.
    """
    return [
        module
        for module in tuple(sys.modules.values())
        if isinstance(module, ModuleType) and _module_is_from_source(module)
    ]


def _singleton_registries() -> list[dict[object, object]]:
    """
    @brief Find Singleton registries referenced by loaded production modules.

    @return Distinct mutable Singleton registries.
    """
    registries: list[dict[object, object]] = []
    for module in _source_modules():
        singleton = getattr(module, "Singleton", None)
        registry = getattr(singleton, "_instances", None)
        if isinstance(registry, dict) and all(
            registry is not seen
            for seen in registries
        ):
            registries.append(registry)

    return registries


class InProcessCareer:
    """
    @brief Isolate a freshly imported Career OS in a temporary repository.
    """

    def __enter__(self) -> Self:
        """
        @brief Create isolated process state and import Career OS afresh.

        @return Active in-process Career OS fixture.
        """
        self._environment = os.environ.copy()
        self._sys_path = sys.path.copy()
        self._modules = sys.modules.copy()
        self._cwd = Path.cwd()
        self._dont_write_bytecode = sys.dont_write_bytecode
        self._saved_registries = [
            (registry, registry.copy())
            for registry in _singleton_registries()
        ]
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None

        try:
            for registry, _ in self._saved_registries:
                registry.clear()

            for name, module in tuple(sys.modules.items()):
                if isinstance(module, ModuleType) and _module_is_from_source(module):
                    sys.modules.pop(name, None)

            self._temporary_directory = tempfile.TemporaryDirectory(
                prefix="career-inprocess-"
            )
            self.base = Path(self._temporary_directory.name)
            self.repo = self.base / "archive with spaces"
            self.cwd = self.base / "external with spaces"
            self.cwd.mkdir()

            isolated_environment = {
                key: value
                for key, value in self._environment.items()
                if not key.startswith(("GIT_", "CAREER_"))
            }
            isolated_environment.update(
                CAREER_REPO_DIR=str(self.repo),
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONUTF8="1",
                GIT_CONFIG_GLOBAL=os.devnull,
                GIT_CONFIG_NOSYSTEM="1",
                GIT_AUTHOR_NAME="In-process test",
                GIT_AUTHOR_EMAIL="inprocess@example.invalid",
                GIT_COMMITTER_NAME="In-process test",
                GIT_COMMITTER_EMAIL="inprocess@example.invalid",
                GIT_TERMINAL_PROMPT="0",
            )
            os.environ.clear()
            os.environ.update(isolated_environment)

            sys.dont_write_bytecode = True
            sys.path.insert(0, str(SOURCE))
            os.chdir(self.cwd)

            self.main = importlib.import_module("main")
            self.paths = importlib.import_module("paths")
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *_: object) -> None:
        """
        @brief Restore all process-global state changed by the fixture.
        """
        for registry in _singleton_registries():
            registry.clear()

        os.chdir(self._cwd)
        os.environ.clear()
        os.environ.update(self._environment)
        sys.dont_write_bytecode = self._dont_write_bytecode
        sys.path[:] = self._sys_path

        for name in tuple(sys.modules):
            if name not in self._modules:
                sys.modules.pop(name, None)
        sys.modules.update(self._modules)

        for registry, contents in self._saved_registries:
            registry.clear()
            registry.update(contents)

        if self._temporary_directory is not None:
            self._temporary_directory.cleanup()

    def dispatch(self, *args: str) -> DispatchResult:
        """
        @brief Run ``main.dispatch`` and capture its observable result.

        @param args Career CLI arguments excluding the executable name.

        @return Exit code and captured standard output and error.
        """
        stdout = StringIO()
        stderr = StringIO()
        previous_argv = sys.argv
        sys.argv = [str(SOURCE / "main.py"), *args]

        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                returncode = self.main.dispatch()
        finally:
            sys.argv = previous_argv

        return DispatchResult(returncode, stdout.getvalue(), stderr.getvalue())

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Run Git against the isolated repository.

        @param args Git arguments excluding the executable name.

        @return Completed Git command result.
        """
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            cwd=self.cwd,
            env=os.environ.copy(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            check=False,
        )


class InProcessCareerTestCase(unittest.TestCase):
    """
    @brief Base class providing a fresh ``career`` fixture to every test.
    """

    career: InProcessCareer

    def setUp(self) -> None:
        """@brief Enter a fresh in-process Career OS fixture."""
        super().setUp()
        context = InProcessCareer()
        self.career = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
