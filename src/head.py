from pathlib import Path
import json
from template.singleton import Singleton
from paths import HEAD_FILE, REPO_DIR
from error import CareerError, DiagnosticKind

REQUIRED_KEYS = ("context", "mission", "thread")

class HeadError(CareerError):
    """
    @brief Exception raised when the Career HEAD state cannot be read.
    """

    def __init__(self, message: str, cause: OSError | ValueError | None = None):
        self.cause = cause
        super().__init__(message, DiagnosticKind.FATAL, returncode=128)

class Head(metaclass=Singleton):

    def __init__(self):
        self.state = self._load()

    def _load(self) -> dict[str, str]:
        try:
            with HEAD_FILE.open("r", encoding="utf-8") as f:
                state = json.load(f)
        except FileNotFoundError as error:
            raise HeadError(
                f"not a Career repository (or any of the parent directories): {REPO_DIR}",
                cause=error,
            ) from error
        except OSError as error:
            raise HeadError(
                f"cannot read Career HEAD state: {error.strerror or str(error)}",
                cause=error,
            ) from error
        except json.JSONDecodeError as error:
            raise HeadError(
                f"Career HEAD state is malformed: {error}",
                cause=error,
            ) from error

        if not isinstance(state, dict) or any(
            key not in state or not isinstance(state[key], str)
            for key in REQUIRED_KEYS
        ):
            raise HeadError("Career HEAD state is malformed: missing required fields")

        if state["thread"] and not state["mission"]:
            raise HeadError("Career HEAD state is inconsistent: thread without a mission")

        if state["mission"] and not state["context"]:
            raise HeadError("Career HEAD state is inconsistent: mission without a context")

        return state

    def _save(self) -> None:
        with HEAD_FILE.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=4)

    def _joinhead(self, *parts: str) -> str:
        return "/".join(
            part
            for part in parts
            if part
        )

    @property
    def path(self) -> str:
        return self._joinhead(
            self.context,
            self.mission,
            self.thread,
        )

    @property
    def context(self) -> str:
        return self.state["context"]

    def set_context(self, context: str) -> None:
        self.state["context"] = context
        self._save()

    @property
    def context_path(self) -> str:
        return self._joinhead(
            self.context,
        )

    def context_path_for(self, context: str) -> str: 
        """ 
        @brief Compose a Career context path without modifying HEAD. 
        @param context Context identifier. 
        @return Logical Career context path. 
        """ 
        return self._joinhead(context)

    @property
    def mission(self) -> str:
        return self.state["mission"]

    def set_mission(self, name: str) -> None:
        self.state["mission"] = name
        self._save()

    @property
    def mission_path(self) -> str:
        return self._joinhead(
            self.context,
            self.mission,
        )

    def mission_path_for(self, mission: str) -> str:
        """ 
        @brief Compose a mission path in the current context. 
        @param mission Mission identifier. 
        @return Logical Career mission path. 
        """ 
        return self._joinhead(
            self.context,
            mission,
        )

    @property
    def thread(self) -> str:
        return self.state["thread"]
    
    def set_thread(self, name: str) -> None:
        self.state["thread"] = name
        self._save()
    
    @property
    def thread_path(self) -> str:
        return self._joinhead(
            self.context,
            self.mission,
            self.thread,
        )

    def thread_path_for(self, thread: str) -> str: 
        """ 
        @brief Compose a thread path in the current mission. 
        @param thread Thread identifier. 
        @return Logical Career thread path. 
        """ 
        return self._joinhead(
            self.context,
            self.mission,
            thread,
        )
    