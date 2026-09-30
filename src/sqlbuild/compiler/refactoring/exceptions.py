"""Expected refactoring errors."""

from __future__ import annotations


class RefactorInputError(ValueError):
    """A rename or move request that cannot be planned at all."""

    code: str = "C950"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class RefactorEditError(RefactorInputError):
    """Two planned edits overlap, which a correct plan never produces."""

    code: str = "C957"


class RefactorWriteError(RefactorInputError):
    """Project files changed between planning and writing."""

    code: str = "C958"
