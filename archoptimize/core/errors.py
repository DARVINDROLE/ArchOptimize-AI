"""Error types. `user_message` is always safe to show in the UI (no keys, no tracebacks)."""

from __future__ import annotations

from dataclasses import dataclass


class ArchOptimizeError(Exception):
    """Base class for every error we raise on purpose."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True)
class InputIssue:
    """One problem in the user's input. `location` is a path like 'design.components[1].type'."""

    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}" if self.location else self.message


class DesignInputError(ArchOptimizeError):
    """The submitted design could not be read or is invalid. Lists every issue found."""

    def __init__(self, issues: list[InputIssue]):
        self.issues = issues
        lines = "\n".join(f"- {issue}" for issue in issues)
        super().__init__(f"The design could not be read:\n{lines}")
