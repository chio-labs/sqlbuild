"""Process-wide access to the render reuse session of the running compile command."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession


class CompileRenderReuseRegistry:
    """Expose one compile command's render reuse session to the rendering code it runs."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._session: CompileRenderReuseSession | None = None

    @contextmanager
    def activated(self, session: CompileRenderReuseSession) -> Iterator[CompileRenderReuseSession]:
        """Make the session available to rendering until the block exits."""

        with self._lock:
            previous: CompileRenderReuseSession | None = self._session
            self._session = session
        try:
            yield session
        finally:
            with self._lock:
                self._session = previous

    def claim(self) -> CompileRenderReuseSession | None:
        """Hand the active session to the first project render only, so it is used once."""

        with self._lock:
            session: CompileRenderReuseSession | None = self._session
            if session is None or not session.claim():
                return None
            return session

    def claim_discovery(self) -> CompileRenderReuseSession | None:
        """Hand the active session to the first project discovery only, so it is used once."""

        with self._lock:
            session: CompileRenderReuseSession | None = self._session
            if session is None or not session.claim_discovery():
                return None
            return session
