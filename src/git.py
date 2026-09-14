import subprocess
from pathlib import Path
import paths

from error import CareerError, DiagnosticKind

class GitError(CareerError):
    """
    @brief Exception raised when a Git command fails.

    @details
    Preserves the complete Git process result and its native diagnostic.
    """

    def __init__(self, result: subprocess.CompletedProcess[str]):
        self.result = result

        message = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"Git command failed with return code {result.returncode}"
        )
        kind = self._diagnostic_kind(message)

        super().__init__(message, kind, result.returncode)

    @staticmethod
    def _diagnostic_kind(message: str) -> DiagnosticKind:
        if message.startswith("error:"):
            return DiagnosticKind.ERROR

        if message.startswith("usage:"):
            return DiagnosticKind.USAGE

        if message.startswith("BUG:"):
            return DiagnosticKind.BUG

        return DiagnosticKind.FATAL

    def __str__(self) -> str:
        prefixes = (
            "fatal:",
            "error:",
            "usage:",
            "BUG:",
        )

        message = self.args[0]

        if message.startswith(prefixes):
            return message

        return f"{self.kind.value}: {message}"

class Git:
    """
    @brief Thin wrapper around the Git command-line interface.

    @details
    Git commands are executed inside the Career repository.
    Native stdout, stderr and return codes are preserved.
    """

    def __init__(self):
        """
        @brief Create a Git wrapper.

        @param repo_dir Absolute physical path of the Git repository.
        """
        self.repo_dir = paths.REPO_DIR

    def _run(self,*args: str, accepted_codes: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
        """
        @brief Execute a Git command.

        @param args Git command arguments.

        @return Native Git command result.
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_dir,
                text=True,
                capture_output=True,
            )
        except OSError as error:
            result = subprocess.CompletedProcess(
                args=["git", *args],
                returncode=128,
                stdout="",
                stderr=f"fatal: unable to run git in '{self.repo_dir}': {error.strerror or str(error)}",
            )
            raise GitError(result) from error

        if result.returncode not in accepted_codes:
            raise GitError(result)
        
        return result

    def init(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Initialize the Git repository.

        @return Native Git initialization result.
        """
        return self._run(
            "init",
            "-b",
            "@career",
        )

    def add(self, name: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Stage a repository resource.

        @param name Repository-relative resource name.

        @return Native Git command result.
        """
        return self._run("add", "--", name)

    def commit(self, message: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Create a Git commit.

        @param message Commit message.

        @return Native Git command result.
        """
        return self._run("commit", "-m", message, accepted_codes=(0, 1))

    def status(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Return the Git repository status.
        """
        return self._run("status")

    def diff(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Compare HEAD with the current filesystem state.
        """
        return self._run(
            "diff-index",
            "--patch",
            "HEAD",
        )

    def create_branch(
        self,
        name: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Create and switch to a new branch.

        @param name Branch name.

        @return Native Git command result.
        """
        return self._run("switch", "-c", name)

    def switch_branch(
        self,
        name: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing branch.

        @param name Branch name.

        @return Native Git command result.
        """
        return self._run("switch", name)

    def remove_branch(
        self,
        name: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Delete an existing branch.

        @param name Branch name to delete.

        @return Native Git command result.
        """
        return self._run("branch", "-d", name)

    def current_branch(self) -> str:
        """
        @brief Return the currently checked-out branch name.
        """
        result = self._run(
            "branch",
            "--show-current",
        )

        return result.stdout.strip()