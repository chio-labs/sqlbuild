"""Model execution errors."""

from __future__ import annotations

from sqlbuild.errors.contracts.exceptions import ExecutorInputError


class EmptyCursorInputsError(ExecutorInputError):
    """Raised when cursor inputs have no rows, so there is no cursor window to process."""

    def __init__(
        self, *, input_names: tuple[str, ...], waiting_on_empty_inputs: bool = False
    ) -> None:
        super().__init__(f"cursor inputs have no rows: {', '.join(input_names)}")
        self.input_names: tuple[str, ...] = input_names
        self.waiting_on_empty_inputs: bool = waiting_on_empty_inputs
