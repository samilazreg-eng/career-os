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

    def has_head(self) -> bool:
        """
        @brief Determine whether HEAD resolves to a commit.

        @return True when HEAD identifies a commit, otherwise False.
        """
        result = self._run(
            "rev-parse",
            "--verify",
            "--quiet",
            "HEAD",
            accepted_codes=(0, 1),
        )

        return result.returncode == 0

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

    def commit_empty(self, message: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Create a Git commit even when nothing is staged.

        @param message Commit message.

        @return Native Git commit result.
        """
        return self._run("commit", "--allow-empty", "-m", message)

    def head_revision(self) -> str:
        """
        @brief Return the full object name of the current HEAD commit.

        @return Full Git object name with surrounding whitespace removed.

        @throws GitError When HEAD does not identify a commit.
        """
        result = self._run("rev-parse", "HEAD")

        return result.stdout.strip()

    def has_staged_changes(self) -> bool:
        """
        @brief Determine whether the index differs from HEAD.

        @return True when staged changes exist, otherwise False.

        @throws GitError When Git returns an exit code other than 0 or 1.
        """
        result = self._run(
            "diff",
            "--cached",
            "--quiet",
            accepted_codes=(0, 1),
        )

        return result.returncode == 1

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
        start_point: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Create and switch to a new branch from a start point.

        @param name Branch name.
        @param start_point Revision from which to create the branch.

        @return Native Git command result.
        """
        return self._run("switch", "-c", name, start_point)

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

    def merge_branch(
        self,
        name: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Merge a branch without committing the result.

        @param name Branch name to merge into the current branch.

        @return Native Git merge result.
        """
        return self._run("merge", "--no-ff", "--no-commit", name)

    def abort_merge(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Abort the current merge and restore its pre-merge state.

        @return Native Git merge-abort result.
        """
        return self._run("merge", "--abort")

    def merge_in_progress(self) -> bool:
        """
        @brief Determine whether Git has recorded an active merge.

        @return True when MERGE_HEAD exists, otherwise False.
        """
        result = self._run(
            "rev-parse",
            "--verify",
            "--quiet",
            "MERGE_HEAD",
            accepted_codes=(0, 1),
        )
        return result.returncode == 0

    def reset_merge(self, revision: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Reset a branch while preserving unrelated working-tree changes.

        @param revision Revision to which the current branch is restored.

        @return Native Git reset result.
        """
        return self._run("reset", "--merge", revision)

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
