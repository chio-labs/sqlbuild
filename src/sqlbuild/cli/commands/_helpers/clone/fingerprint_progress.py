"""Clone fingerprint finalization progress reporting."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands._helpers.clone.output import (
    render_clone_fingerprint_interrupted_line,
    render_clone_fingerprint_progress_line,
)
from sqlbuild.executor.clone.types import CloneFingerprintProgressReporter


class _CloneFingerprintProgressReporter:
    def __init__(self, *, stream: TextIO, use_color: bool) -> None:
        self._stream: TextIO = stream
        self._use_color: bool = use_color
        self._confirmed: int = 0
        self._total: int = 0
        self._pending_identities: tuple[str, ...] = ()

    def __call__(self, *, completed: int, total: int, pending_identities: tuple[str, ...]) -> None:
        self._confirmed = completed
        self._total = total
        self._pending_identities = pending_identities
        if completed == 0:
            return
        self._stream.write(
            render_clone_fingerprint_progress_line(
                completed=completed,
                total=total,
                use_color=self._use_color,
            )
            + "\n"
        )
        self._stream.flush()

    def write_interrupted(self) -> None:
        if self._total <= self._confirmed:
            return
        self._stream.write(
            render_clone_fingerprint_interrupted_line(
                completed=self._confirmed,
                total=self._total,
                pending_identities=self._pending_identities,
                use_color=self._use_color,
            )
            + "\n"
        )
        self._stream.flush()


def create_clone_fingerprint_progress_reporter(
    *, stream: TextIO, use_color: bool
) -> CloneFingerprintProgressReporter:
    """Create a stateful reporter for one clone finalization phase."""

    return _CloneFingerprintProgressReporter(stream=stream, use_color=use_color)
