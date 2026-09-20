from pathlib import Path, PurePosixPath
import shutil
from paths import REPO_DIR, CAREER_OS_DIR
from error import CareerError, DiagnosticKind

class WorkingTreeError(CareerError):
    """
    @brief Exception raised by WorkingTree operations.

    @details
    WorkingTreeError preserves the Git-like diagnostic category while
    retaining the original operating-system exception when applicable.
    """

    def __init__(
        self,
        message: str,
        kind: DiagnosticKind = DiagnosticKind.FATAL,
        cause: OSError | None = None,
    ):
        """
        @brief Construct a WorkingTree exception.

        @param message Human-readable diagnostic message.
        @param kind Git-like diagnostic category.
        @param cause Optional original operating-system exception.
        """
        self.cause = cause
        super().__init__(message, kind, returncode=128)

class WorkingTree:
    """
    @brief Physical working tree of the Career repository.

    @details
    WorkingTree is responsible for the filesystem representation of Career
    resources and structural paths inside the repository.

    Career paths are repository-relative logical paths. Physical filesystem
    paths are resolved and manipulated exclusively by this class.
    """

    MARKER_NAME = ".career"

    def __init__(self):
        """
        @brief Construct a Career tree.

        @param repo_dir Absolute physical directory containing the Career
                        tree.
        """
        self.repo_dir = REPO_DIR

    def init(self) -> None:
        """
        @brief Create the physical Career repository directory.

        @throws WorkingTreeError If the target directory is the Career OS
                           installation itself, or lies inside it.
        """
        if self.repo_dir == CAREER_OS_DIR or CAREER_OS_DIR in self.repo_dir.parents:
            raise WorkingTreeError(
                message=(
                    "refusing to initialize a Career repository inside "
                    f"the Career OS installation ('{CAREER_OS_DIR}')"
                )
            )

        try:
            self.repo_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as error:
            raise WorkingTreeError(
                message=(
                    f"cannot create directory '{self.repo_dir}': "
                    f"{error.strerror or str(error)}"
                ),
                cause=error,
            ) from error


    def resolve_dir(self, path_name: str) -> Path:
        """
        @brief Resolve a Career path to its physical repository directory.

        @param path_name Repository-relative Career path.

        @return Absolute physical directory corresponding to the Career path.

        @throws WorkingTreeError If the path is absolute or attempts to escape
                           the repository using '..'.
        """
        if "\\" in path_name or ":" in path_name:
            raise WorkingTreeError(
                message="Career path cannot contain Windows path separators or drive letters"
            )

        path = PurePosixPath(path_name)

        if path.is_absolute():
            raise WorkingTreeError(
                message="Career path must be repository-relative"
            )

        if ".." in path.parts:
            raise WorkingTreeError(
                message="Career path cannot escape the repository"
            )

        repo_root = self.repo_dir.resolve()
        target_dir = (repo_root / Path(*path.parts)).resolve() if path.parts else repo_root

        if target_dir != repo_root and repo_root not in target_dir.parents:
            raise WorkingTreeError(
                message="Career path escapes the repository"
            )

        return target_dir

    def capture(
        self,
        source_dir: Path,
        destination_file: str,
    ) -> str:
        """
        @brief Copy an external resource into the Career repository.

        @param source_dir Absolute physical path of the external resource.
        @param destination_file Career path where the resource is captured.

        @return Repository-relative Career path of the captured resource.

        @throws ValueError If source_dir is not absolute.
        @throws WorkingTreeError If the source resource does not exist or is
                           not a regular file.
        """
        if not source_dir.is_absolute():
            raise ValueError(
                "External resource must use an absolute path"
            )

        if not source_dir.exists():
            raise WorkingTreeError(
                message=f"pathspec '{source_dir}' did not match any files"
            )

        if not source_dir.is_file():
            raise WorkingTreeError(
                message=f"cannot capture '{source_dir}': not a regular file"
            )

        if not (self.repo_dir / ".git").exists():
            raise WorkingTreeError(
                message="not a Career repository (run 'career init' first)"
            )

        destination_dir = self.resolve_dir(destination_file)

        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise WorkingTreeError(
                message=(
                    f"cannot create directory '{destination_dir}': "
                    f"{error.strerror or str(error)}"
                ),
                cause=error,
            ) from error

        destination_dir = destination_dir / source_dir.name

        if source_dir != destination_dir:
            try:
                shutil.copy2(source_dir, destination_dir)

            except OSError as error:
                raise WorkingTreeError(
                    message=(
                        f"cannot copy '{source_dir}' to '{destination_dir}': "
                        f"{error.strerror or str(error)}"
                    ),
                    cause=error,
                ) from error
        
        resource_path = (
            PurePosixPath(destination_file)
            / source_dir.name
        )

        return resource_path.as_posix()

    def create_dir(self, path_name: str) -> str:
        """
        @brief Materialize a Career path in the repository.

        @details
        Git does not version empty directories. A '.career' marker is created
        so that the structural directory can be staged and committed.

        @param path_name Repository-relative Career path.

        @return Repository-relative path of the created marker file.
        """
        target_dir = self.resolve_dir(path_name)

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise WorkingTreeError(
                message=(
                    f"cannot create directory '{target_dir}': "
                    f"{error.strerror or str(error)}"
                ),
                cause=error,
            ) from error

        marker_dir = target_dir / self.MARKER_NAME
        marker_dir.touch(exist_ok=True)

        marker_path = (
            PurePosixPath(path_name)
            / self.MARKER_NAME
        )

        return marker_path.as_posix()

    def remove_marker(self, path_name: str) -> str:
        """
        @brief Remove a Career scope marker and its directory if empty.

        @param path_name Repository-relative Career path whose marker is removed.

        @return Repository-relative path of the removed marker file.
        """
        target_dir = self.resolve_dir(path_name)
        marker = target_dir / self.MARKER_NAME

        try:
            marker.unlink()
            if not any(target_dir.iterdir()):
                target_dir.rmdir()
        except OSError as error:
            raise WorkingTreeError(
                message=(
                    f"cannot remove scope marker '{marker}': "
                    f"{error.strerror or str(error)}"
                ),
                cause=error,
            ) from error

        return (
            PurePosixPath(path_name)
            / self.MARKER_NAME
        ).as_posix()
