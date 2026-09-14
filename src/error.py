from enum import Enum


class DiagnosticKind(Enum):
    FATAL = "fatal"
    ERROR = "error"
    USAGE = "usage"
    BUG = "BUG"

class CareerError(RuntimeError):
    def __init__(
        self,
        message: str,
        kind: DiagnosticKind,
        returncode: int,
    ):
        self.returncode = returncode
        self.kind = kind
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.kind.value}: {self.args[0]}"