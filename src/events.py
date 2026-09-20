"""Immutable, versioned Career OS business events.

See ``docs/events.md`` for the event contract.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import ClassVar


SCHEMA_VERSION = "1"
_FULL_OBJECT_NAME = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


@dataclass(frozen=True)
class HeadSnapshot:
    """
    @brief Immutable copy of the Career Head hierarchy.
    """

    context: str
    mission: str
    thread: str


@dataclass(frozen=True)
class CareerEvent:
    """
    @brief Common immutable fields and serialization for Career events.
    """

    event_id: str
    operation_id: str
    occurred_at: datetime
    head: HeadSnapshot
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    event_type: ClassVar[str]

    def __post_init__(self) -> None:
        """@brief Validate the common event timestamp contract."""
        if type(self) is CareerEvent:
            raise TypeError("CareerEvent cannot be instantiated directly")

        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")

        if self.occurred_at.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must be timezone-aware UTC")

        if self.occurred_at.microsecond != 0:
            raise ValueError("occurred_at must have whole-second precision")

    def to_dict(self) -> dict[str, object]:
        """
        @brief Convert the event to a JSON-compatible dictionary.

        @return Versioned event data without free-form payload fields.
        """
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "operation_id": self.operation_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(timespec="seconds"),
            "head": {
                "context": self.head.context,
                "mission": self.head.mission,
                "thread": self.head.thread,
            },
        }


@dataclass(frozen=True)
class CommitInitiated(CareerEvent):
    """@brief Event published when a public Career commit begins."""

    event_type: ClassVar[str] = "career.commit.initiated"


@dataclass(frozen=True)
class CommitInReview(CareerEvent):
    """@brief Event published when a Career commit enters review."""

    event_type: ClassVar[str] = "career.commit.in_review"


@dataclass(frozen=True)
class CommitReviewed(CareerEvent):
    """@brief Event published after review and Workspace commit creation."""

    workspace_revision: str
    event_type: ClassVar[str] = "career.commit.reviewed"

    def __post_init__(self) -> None:
        """@brief Validate the timestamp and committed Workspace revision."""
        super().__post_init__()
        _validate_workspace_revision(self.workspace_revision)

    def to_dict(self) -> dict[str, object]:
        """
        @brief Convert the reviewed event to a JSON-compatible dictionary.

        @return Event data including the full Workspace revision.
        """
        return {
            **super().to_dict(),
            "workspace_revision": self.workspace_revision,
        }


@dataclass(frozen=True)
class CommitCompleted(CareerEvent):
    """@brief Event published after successful commit capitalisation."""

    workspace_revision: str
    event_type: ClassVar[str] = "career.commit.completed"

    def __post_init__(self) -> None:
        """@brief Validate the timestamp and capitalised Workspace revision."""
        super().__post_init__()
        _validate_workspace_revision(self.workspace_revision)

    def to_dict(self) -> dict[str, object]:
        """
        @brief Convert the completed event to a JSON-compatible dictionary.

        @return Event data including the full Workspace revision.
        """
        return {
            **super().to_dict(),
            "workspace_revision": self.workspace_revision,
        }


def _validate_workspace_revision(workspace_revision: str) -> None:
    """
    @brief Validate a full SHA-1 or SHA-256 lowercase Git object name.

    @param workspace_revision Workspace commit object name.
    """
    if not isinstance(workspace_revision, str) or not _FULL_OBJECT_NAME.fullmatch(
        workspace_revision
    ):
        raise ValueError(
            "workspace_revision must be a full lowercase SHA-1 or SHA-256 object name"
        )
