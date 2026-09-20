import subprocess

from datetime import datetime, timezone
from pathlib import Path
import uuid

from eventbus import CareerEventBus, EventDispatchError, EventPublisher
from events import (
    CareerEvent,
    CommitCompleted,
    CommitInitiated,
    CommitInReview,
    CommitReviewed,
    HeadSnapshot,
)
from head import Head
from repository import Repository

from error import CareerError, DiagnosticKind

class WorkspaceError(CareerError):
    """
    @brief Exception raised when a Workspace operation cannot be performed.
    """

    def __init__(
        self,
        message: str,
        kind: DiagnosticKind = DiagnosticKind.FATAL,
    ):
        self.message = message
        self.kind = kind

        super().__init__(message, returncode=128, kind=self.kind)

    def __str__(self) -> str:
        return f"{self.kind.value}: {self.message}"


class CommitEventsError(RuntimeError):
    """@brief Aggregate event-delivery failures from a completed commit."""

    def __init__(
        self,
        result: subprocess.CompletedProcess[str],
        errors: list[EventDispatchError],
    ):
        """
        @brief Preserve the Git result and collected delivery failures.

        @param result Result returned by the Workspace Git commit.
        @param errors Event dispatch failures in publication order.
        """
        self.result = result
        self.errors = errors
        super().__init__(f"{len(errors)} commit event publication(s) failed")


class Workspace:
    """
    @brief Manage the active Career workspace.

    @details
    Workspace owns the Career HEAD lifecycle and manages structural navigation
    across contexts, missions and threads.

    It is responsible for:

    - composing structural repository references through Head;
    - creating Career structural branches;
    - switching between Career structural branches;
    - finishing structural elements;
    - keeping HEAD synchronized with the active repository position.

    Git branch naming convention:

        @career
        <context>/@context
        <context>/<mission>/@mission
        <context>/<mission>/<thread>/@thread
    """

    def __init__(self):
        """
        @brief Construct the active Career workspace.
        """
        self.head = Head()
        self.repo = Repository()
        self.events: EventPublisher = CareerEventBus()

    def init(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Initialize the Career archive.

        @return Result of the repository initialization.
        """
        return self.repo.init()

    def add(self, resource_dir: Path) -> subprocess.CompletedProcess[str]:
        """
        @brief Capture an external resource at the current Career position.

        @param resource_dir Physical path of the resource to capture.
        """
        return self.repo.add(
            resource_dir,
            self.head.path,
        )

    def commit(self, message: str) -> subprocess.CompletedProcess[str]:
        """
        @brief Capitalize the currently staged Career resources.

        See ``docs/events.md`` for the event publication contract.

        @param message Description of the capitalization.
        """
        head = HeadSnapshot(
            context=self.head.context,
            mission=self.head.mission,
            thread=self.head.thread,
        )

        if not self.repo.has_staged_changes():
            return self.repo.commit(message)

        operation_id = str(uuid.uuid4())
        errors: list[EventDispatchError] = []

        self._publish_event(
            CommitInitiated(
                event_id=str(uuid.uuid4()),
                operation_id=operation_id,
                occurred_at=self._event_time(),
                head=head,
            ),
            errors,
        )
        self._publish_event(
            CommitInReview(
                event_id=str(uuid.uuid4()),
                operation_id=operation_id,
                occurred_at=self._event_time(),
                head=head,
            ),
            errors,
        )

        result = self.repo.commit(message)
        if result.returncode != 0:
            if errors:
                raise CommitEventsError(result, errors)
            return result

        revision = self.repo.head_revision()
        reviewed_succeeded = self._publish_event(
            CommitReviewed(
                event_id=str(uuid.uuid4()),
                operation_id=operation_id,
                occurred_at=self._event_time(),
                head=head,
                workspace_revision=revision,
            ),
            errors,
        )

        if reviewed_succeeded:
            self._publish_event(
                CommitCompleted(
                    event_id=str(uuid.uuid4()),
                    operation_id=operation_id,
                    occurred_at=self._event_time(),
                    head=head,
                    workspace_revision=revision,
                ),
                errors,
            )

        if errors:
            raise CommitEventsError(result, errors)

        return result

    @staticmethod
    def _event_time() -> datetime:
        """
        @brief Return the current UTC time with Git-like second precision.

        @return Timezone-aware UTC timestamp without sub-seconds.
        """
        return datetime.now(timezone.utc).replace(microsecond=0)

    def _publish_event(
        self,
        event: CareerEvent,
        errors: list[EventDispatchError],
    ) -> bool:
        """
        @brief Publish an event while collecting handler failures.

        @param event Immutable event to publish.
        @param errors Destination for aggregate dispatch failures.

        @return True when every handler succeeded, otherwise False.
        """
        try:
            self.events.publish(event)
        except EventDispatchError as error:
            errors.append(error)
            return False

        return True

    def status(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Display the current Career repository status.
        """
        return self.repo.status()

    def diff(self) -> subprocess.CompletedProcess[str]:
        """
        @brief Display changes since the current HEAD commit.
        """
        return self.repo.diff()

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

        @return Result of the capitalization commit.
        """
        context_path = self.head.context_path_for(id)
        context_branch = context_path + "/@context"

        self.repo.create_branch(
            context_branch,
            context_path,
        )

        result = self.repo.commit(f"Start context {id}")

        self.head.set_context(id)
        self.head.set_mission("")
        self.head.set_thread("")

        return result

    def switch_context(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing Career context.

        @param id Identifier of the target context.

        @return Result of the repository switch operation.
        """
        context_path = self.head.context_path_for(id)
        context_branch = context_path + "/@context"

        result = self.repo.switch_branch(
            context_branch
        )

        self.head.set_context(id)
        self.head.set_mission("")
        self.head.set_thread("")

        return result

    def finish_context(
        self,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Finish the current context and return to Career root.

        @return Result of the capitalization commit.
        """
        if not self.head.context:
            raise WorkspaceError(
                "cannot finish a context without an active context."
            )
        
        context_id = self.head.context
        context_path = self.head.context_path
        context_branch = context_path + "/@context"

        self.repo.switch_branch("@career")

        self.repo.remove_branch(
            context_branch,
            context_path,
        )

        result = self.repo.commit(
            f"Finish context {context_id}"
        )

        self.head.set_context("")
        self.head.set_mission("")
        self.head.set_thread("")

        return result

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

        @return Result of the capitalization commit.
        """
        if not self.head.context:
            raise WorkspaceError(
                "cannot start a mission without an active context."
            )

        mission_path = self.head.mission_path_for(id)
        mission_branch = mission_path + "/@mission"

        self.repo.create_branch(
            mission_branch,
            mission_path,
        )

        result = self.repo.commit(
            f"Start mission {id}"
        )

        self.head.set_mission(id)
        self.head.set_thread("")

        return result

    def switch_mission(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing mission in the current context.

        @param id Identifier of the target mission.

        @return Result of the repository switch operation.
        """
        if not self.head.context:
            raise WorkspaceError(
                "cannot switch to a mission without an active context."
            )
        
        mission_path = self.head.mission_path_for(id)
        mission_branch = mission_path + "/@mission"

        result = self.repo.switch_branch(
            mission_branch
        )

        self.head.set_mission(id)
        self.head.set_thread("")

        return result

    def finish_mission(
        self,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Finish the current mission and return to its parent context.

        @return Result of the capitalization commit.
        """
        if not self.head.mission:
            raise WorkspaceError(
                "cannot finish a mission without an active mission."
            )

        mission_id = self.head.mission
        mission_path = self.head.mission_path
        mission_branch = mission_path + "/@mission"

        context_branch = (
            self.head.context_path
            + "/@context"
        )

        self.repo.switch_branch(
            context_branch
        )

        self.repo.remove_branch(
            mission_branch,
            mission_path,
        )

        result = self.repo.commit(
            f"Finish mission {mission_id}"
        )

        self.head.set_mission("")
        self.head.set_thread("")

        return result

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

        @return Result of the capitalization commit.
        """
        if not self.head.mission:
            raise WorkspaceError(
                "cannot start a thread without an active mission."
            )
        
        thread_path = self.head.thread_path_for(id)
        thread_branch = thread_path + "/@thread"

        self.repo.create_branch(
            thread_branch,
            thread_path,
        )

        result = self.repo.commit(
            f"Start thread {id}"
        )

        self.head.set_thread(id)

        return result

    def switch_thread(
        self,
        id: str,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Switch to an existing thread in the current mission.

        @param id Identifier of the target thread.

        @return Result of the repository switch operation.
        """
        if not self.head.mission:
            raise WorkspaceError(
                "cannot switch to a thread without an active mission."
            )
        
        thread_path = self.head.thread_path_for(id)
        thread_branch = thread_path + "/@thread"

        result = self.repo.switch_branch(
            thread_branch
        )

        self.head.set_thread(id)

        return result

    def finish_thread(
        self,
    ) -> subprocess.CompletedProcess[str]:
        """
        @brief Finish the current thread and return to its parent mission.

        @return Result of the capitalization commit.
        """
        if not self.head.thread:
            raise WorkspaceError(
                "cannot finish a thread without an active thread."
            )

        thread_id = self.head.thread
        thread_path = self.head.thread_path
        thread_branch = thread_path + "/@thread"

        mission_branch = (
            self.head.mission_path
            + "/@mission"
        )

        self.repo.switch_branch(
            mission_branch
        )

        self.repo.remove_branch(
            thread_branch,
            thread_path,
        )

        result = self.repo.commit(
            f"Finish thread {thread_id}"
        )

        self.head.set_thread("")

        return result
