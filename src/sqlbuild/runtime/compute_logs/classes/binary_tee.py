"""Failure-isolated binary stream tee."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.runtime.compute_logs._helpers.accepted_write import accepted_write_count
from sqlbuild.runtime.compute_logs.types import ComputeLogStorage, ComputeLogStream


class BinaryComputeLogTee:
    """Retain accepted bytes; a None sink result means the full write was accepted."""

    def __init__(
        self,
        *,
        sink: Any,
        storage: ComputeLogStorage,
        invocation_id: str,
        stream: ComputeLogStream,
        encoding: str = "utf-8",
        errors: str = "surrogateescape",
        text_sink: bool = False,
        before_write: Callable[[], None] | None = None,
        failure_callback: Callable[[Exception], None] | None = None,
    ) -> None:
        self._sink: Any = sink
        self._storage: ComputeLogStorage = storage
        self._invocation_id: str = invocation_id
        self._stream: ComputeLogStream = stream
        self._encoding: str = encoding
        self._errors: str = errors
        self._text_sink: bool = text_sink
        self._before_write: Callable[[], None] | None = before_write
        self._failure_callback: Callable[[Exception], None] | None = failure_callback
        self._storage_failed: bool = False

    def write(self, data: bytes | bytearray) -> int:
        """Preserve sink behavior while isolating capture append failures."""

        offered: bytes = bytes(data)
        if self._before_write is not None:
            self._before_write()
        accepted: bytes
        if not self._text_sink:
            result: object = self._sink.write(offered)
            accepted = offered[: accepted_write_count(result=result, offered_count=len(offered))]
        else:
            text: str = offered.decode(self._encoding, self._errors)
            result = self._sink.write(text)
            accepted_text: str = text[
                : accepted_write_count(result=result, offered_count=len(text))
            ]
            accepted = accepted_text.encode(self._encoding, self._errors)
        if accepted and not self._storage_failed:
            try:
                self._storage.append(
                    invocation_id=self._invocation_id, stream=self._stream, data=accepted
                )
            except Exception as error:
                self._storage_failed = True
                if self._failure_callback is not None:
                    self._failure_callback(error)
        return result if isinstance(result, int) else len(offered)

    def flush(self) -> None:
        """Flush the original sink without closing it."""

        self._sink.flush()

    def close(self) -> None:
        """Flush but preserve ownership of the original process sink."""

        self.flush()

    @property
    def closed(self) -> bool:
        return bool(getattr(self._sink, "closed", False))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sink, name)
