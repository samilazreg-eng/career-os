from pathlib import Path
import subprocess

from eventbus import EventDispatchError
from repository import Repository
from workspace import CommitEventsError, Workspace


class CommitProcess(subprocess.CompletedProcess[str]):
    """@brief Git commit result enriched with event-delivery warnings."""

    def __init__(
        self,
        result: subprocess.CompletedProcess[str],
        errors: list[EventDispatchError],
    ):
        """
        @brief Preserve a Git result and append ordered delivery warnings.

        @param result Native result returned by the Workspace Git commit.
        @param errors Event dispatch failures in publication order.
        """
        warnings = "".join(
            f"warning: event delivery failed ({error.event.event_type}): "
            f"{type(failure).__name__}: {failure}\n"
            for error in errors
            for _, failure in error.failures
        )
        stderr = result.stderr or ""
        if stderr and not stderr.endswith("\n"):
            stderr += "\n"

        super().__init__(
            args=result.args,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=stderr + warnings,
        )
        self.errors: list[EventDispatchError] = list(errors)


class Career:
    """
    @brief Main Career OS application façade.

    @details
    Career exposes the public Career OS operations used by the CLI.

    Workspace owns the active Career state and all operations performed
    within that state, including resource capture, capitalization and
    context/mission/thread lifecycle management.

    Repository is accessed directly only for Career initialization.
    """

    def __init__(self):
        """
        @brief Construct Career OS.
        """
        self.repo = Repository()
        self._workspace = None

    @property
    def workspace(self) -> Workspace:
        """
        @brief Return the active Career workspace.

        @details
        The workspace is created lazily so that `career init` can operate
        before a Career HEAD or workspace state exists.

        @return Active Career workspace.
        """
        if self._workspace is None:
            self._workspace = Workspace()

        return self._workspace

    # ------------------------------------------------------------------
    # Career
    # ------------------------------------------------------------------

    def init(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Initialize the Career archive.

        @return Result of the repository initialization.
        """
        return self.repo.init()

    # ------------------------------------------------------------------
    # Current work
    # ------------------------------------------------------------------

    def add(
        self,
        resource_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Capture an external resource at the current Career position.

        @param resource_dir Physical path of the external resource.

        @return Result of the capture operation.
        """
        return self.workspace.add(resource_dir)

    def commit(
        self,
        message: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Capitalize the currently staged Career resources.

        @param message Description of the capitalization.

        @return Result of the commit operation.
        """
        try:
            return self.workspace.commit(message)
        except CommitEventsError as error:
            return CommitProcess(error.result, error.errors)

    def status(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Display the current Career workspace status.

        @return Result of the status operation.
        """
        return self.workspace.status()

    def diff(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Display changes since the current HEAD commit.

        @return Result of the diff operation.
        """
        return self.workspace.diff()

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def start_context(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Start a new Career context.

        @param id Identifier of the new context.

        @return Result of the context start operation.
        """
        return self.workspace.start_context(id)

    def switch_context(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing Career context.

        @param id Identifier of the target context.

        @return Result of the context switch operation.
        """
        return self.workspace.switch_context(id)

    def finish_context(
        self,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Finish the current Career context.

        @return Result of the context finish operation.
        """
        return self.workspace.finish_context()

    # ------------------------------------------------------------------
    # Mission
    # ------------------------------------------------------------------

    def start_mission(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Start a new mission in the current context.

        @param id Identifier of the new mission.

        @return Result of the mission start operation.
        """
        return self.workspace.start_mission(id)

    def switch_mission(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing mission.

        @param id Identifier of the target mission.

        @return Result of the mission switch operation.
        """
        return self.workspace.switch_mission(id)

    def finish_mission(
        self,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Finish the current mission.

        @return Result of the mission finish operation.
        """
        return self.workspace.finish_mission()

    # ------------------------------------------------------------------
    # Thread
    # ------------------------------------------------------------------

    def start_thread(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Start a new thread in the current mission.

        @param id Identifier of the new thread.

        @return Result of the thread start operation.
        """
        return self.workspace.start_thread(id)

    def switch_thread(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing thread.

        @param id Identifier of the target thread.

        @return Result of the thread switch operation.
        """
        return self.workspace.switch_thread(id)

    def finish_thread(
        self,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Finish the current thread.

        @return Result of the thread finish operation.
        """
        return self.workspace.finish_thread()
