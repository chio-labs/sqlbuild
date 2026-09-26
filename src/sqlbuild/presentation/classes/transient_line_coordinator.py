"""Coordinator for one live transient terminal line and persistent writes."""

from __future__ import annotations

import threading
from typing import TextIO

from sqlbuild.presentation.types import TransientLineOwner


class TransientLineCoordinator:
    """Keep persistent terminal lines from landing on a live spinner or status line."""

    def __init__(self) -> None:
        self.lock: threading.RLock = threading.RLock()
        self._active: tuple[TextIO, TransientLineOwner] | None = None

    def claim(self, *, stream: TextIO, owner: TransientLineOwner) -> None:
        """Record the owner of the transient line currently drawn on a terminal stream."""

        with self.lock:
            self._active = (stream, owner)

    def release(self, *, owner: TransientLineOwner) -> None:
        """Forget a transient owner once its line is no longer drawn."""

        with self.lock:
            if self._active is not None and self._active[1] is owner:
                self._active = None

    def write_persistent(self, *, stream: TextIO, text: str) -> None:
        """Write lasting text, clearing and then redrawing any live transient line."""

        with self.lock:
            owner: TransientLineOwner | None = self._interrupted_owner(stream=stream)
            if owner is not None:
                owner.clear_transient_line()
            stream.write(text)
            stream.flush()
            if owner is not None:
                owner.redraw_transient_line()

    def _interrupted_owner(self, *, stream: TextIO) -> TransientLineOwner | None:
        if self._active is None:
            return None
        owner_stream: TextIO
        owner: TransientLineOwner
        owner_stream, owner = self._active
        if owner_stream is stream or (_is_tty(owner_stream) and _is_tty(stream)):
            return owner
        return None


def _is_tty(stream: TextIO) -> bool:
    return hasattr(stream, "isatty") and stream.isatty()
