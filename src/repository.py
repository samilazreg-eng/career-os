from pathlib import Path
import json
import subprocess
from template.singleton import Singleton
from git import Git
from workingtree import WorkingTree
from paths import REPO_DIR, HEAD_FILE

class Repository(metaclass=Singleton):
    """
    @brief Career repository façade.

    @details
    Repository is the infrastructure boundary between the Career domain and the
    underlying filesystem/Git implementation.

    It coordinates Workspace filesystem operations with Git version-control
    operations.
    """

    def __init__(self):
        """
        @brief Construct the Career repository.

        @param repo_dir Physical root directory of the Career workspace.
        """
        self.working_tree = WorkingTree()
        self.git = Git()

    def init(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Initialize the Career workspace and Git repository.

        @details
        Creates the physical Career repository directory and initializes
        Git with '@career' as the root branch. When HEAD is unborn, creates
        the empty Career root commit.

        @return Result of the Git initialization.
        """
        self.working_tree.init()

        result = self.git.init()

        exclude_file = REPO_DIR / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        exclude_contents = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
        if ".career/" not in exclude_contents.splitlines():
            with exclude_file.open("a", encoding="utf-8") as f:
                if exclude_contents and not exclude_contents.endswith("\n"):
                    f.write("\n")
                f.write(".career/\n")

        HEAD_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not HEAD_FILE.exists():
            HEAD_FILE.write_text(
                json.dumps({"context": "", "mission": "", "thread": ""}),
                encoding="utf-8",
            )

        if not self.git.has_head():
            self.git.commit_empty("Initialize Career archive")

        return result

    def add(
        self,
        resource_dir: Path,
        destination_path: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Capture and stage an external resource.

        @param resource_dir Absolute physical path of the external resource.
        @param destination_path Career path receiving the resource.

        @return Repository-relative path of the captured resource.
        """
        resource_path = self.working_tree.capture(
            resource_dir,
            destination_path,
        )

        return self.git.add(resource_path)

    def create_branch(
        self,
        branch_name: str,
        parent_branch: str,
        workspace_path: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Create a Git branch and materialize its Career structure.

        @param branch_name Git branch name.
        @param parent_branch Structural parent from which to create the branch.
        @param workspace_path Career path associated with the branch.
        """
        result = self.git.create_branch(branch_name, parent_branch)

        marker_path = self.working_tree.create_dir(
            workspace_path
        )

        result = self.git.add(marker_path)

        return result

    def switch_branch(self, branch_name: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch the repository to another Career branch.

        @param branch_name Git branch name to activate.
        """
        return self.git.switch_branch(branch_name)

    def current_branch(self) -> str:
        """
        @brief Return the currently checked-out Git branch name.

        @return Branch name, or an empty string when HEAD is detached.
        """
        return self.git.current_branch()

    def remove_branch(self, branch_name: str, branch_path: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Remove a Git branch from the repository.

        @param branch_name Git branch name to remove.
        """
        removed = self.working_tree.remove_dir(branch_path)

        if removed:
            self.git.add(branch_path)

        return self.git.remove_branch(branch_name)

    def commit(self, message: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Commit the current staged Career state.

        @param message Commit message associated with this Career commit.
        """
        return self.git.commit(message)

    def head_revision(self) -> str:
        """
        @brief Return the full object name of the current HEAD commit.

        @return Full Git object name of HEAD.
        """
        return self.git.head_revision()

    def has_staged_changes(self) -> bool:
        """
        @brief Determine whether the repository index contains changes.

        @return True when staged changes exist, otherwise False.
        """
        return self.git.has_staged_changes()

    def status(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Display the current repository status.
        """
        return self.git.status()

    def diff(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Compare the current filesystem state with HEAD.
        """
        return self.git.diff()
