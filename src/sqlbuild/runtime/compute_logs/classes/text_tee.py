"""Failure-isolated text stream tee with binary buffer support."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.runtime.compute_logs._helpers.accepted_write import accepted_write_count
from sqlbuild.runtime.compute_logs.classes.binary_tee import BinaryComputeLogTee
from sqlbuild.runtime.compute_logs.types import ComputeLogStorage, ComputeLogStream


class TextComputeLogTee:
    """Capture accepted text at its Python encoding boundary while buffer writes remain raw."""

    def __init__(
        self,
        *,
        sink: Any,
        storage: ComputeLogStorage,
        invocation_id: str,
        stream: ComputeLogStream,
        failure_callback: Callable[[Exception], None] | None = None,
    ) -> None:
        self._sink: Any = sink
        self._storage: ComputeLogStorage = storage
        self._invocation_id: str = invocation_id
        self._stream: ComputeLogStream = stream
        self._encoding: str = getattr(sink, "encoding", None) or "utf-8"
        self._errors: str = getattr(sink, "errors", None) or "strict"
        self._failure_callback: Callable[[Exception], None] | None = failure_callback
        self._storage_failed: bool = False
        binary_sink: Any = getattr(sink, "buffer", sink)
        binary_uses_text_sink: bool = binary_sink is sink
        self._buffer: BinaryComputeLogTee = BinaryComputeLogTee(
            sink=binary_sink,
            storage=storage,
            invocation_id=invocation_id,
            stream=stream,
            encoding=self._encoding,
            errors="surrogateescape",
            text_sink=binary_uses_text_sink,
            before_write=sink.flush,
            failure_callback=failure_callback,
        )

    def write(self, text: str) -> int:
        """Preserve the text sink return value and append only after it succeeds."""

        result: object = self._sink.write(text)
        accepted_count: int = accepted_write_count(result=result, offered_count=len(text))
        if accepted_count and not self._storage_failed:
            try:
                emitted: bytes = text[:accepted_count].encode(self._encoding, self._errors)
                self._storage.append(
                    invocation_id=self._invocation_id, stream=self._stream, data=emitted
                )
            except Exception as error:
                self._storage_failed = True
                if self._failure_callback is not None:
                    self._failure_callback(error)
        return result if isinstance(result, int) else len(text)

    def flush(self) -> None:
        """Flush the existing text sink without changing its ownership."""

        self._sink.flush()

    def close(self) -> None:
        """Flush but do not close the process-owned sink."""

        self.flush()

    @property
    def buffer(self) -> BinaryComputeLogTee:
        return self._buffer

    @property
    def encoding(self) -> str:
        return self._encoding

    @property
    def errors(self) -> str:
        return self._errors

    @property
    def closed(self) -> bool:
        return bool(getattr(self._sink, "closed", False))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sink, name)
