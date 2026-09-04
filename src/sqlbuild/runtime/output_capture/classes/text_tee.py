"""Transparent text stream tee for output capture."""

from __future__ import annotations

from typing import Any

from sqlbuild.runtime.output_capture.classes.binary_tee import BinaryOutputTee
from sqlbuild.runtime.output_capture.classes.dispatcher import OutputCaptureDispatcher
from sqlbuild.runtime.output_capture.types import OutputStream


class TextOutputTee:
    """Preserve the original text stream behavior and capture only accepted text."""

    def __init__(
        self, *, sink: Any, dispatcher: OutputCaptureDispatcher, stream: OutputStream
    ) -> None:
        self._sink: Any = sink
        self._dispatcher: OutputCaptureDispatcher = dispatcher
        self._stream: OutputStream = stream
        encoding: str = getattr(sink, "encoding", None) or "utf-8"
        binary_sink: Any = getattr(sink, "buffer", sink)
        self._buffer = BinaryOutputTee(
            sink=binary_sink,
            dispatcher=dispatcher,
            stream=stream,
            encoding=encoding,
            text_sink=binary_sink is sink,
        )

    def write(self, text: str) -> int:
        result: object = self._sink.write(text)
        accepted_count: int = result if isinstance(result, int) else len(text)
        try:
            self._dispatcher.append(stream=self._stream, text=text[:accepted_count])
        except BaseException:
            pass
        return accepted_count

    def flush(self) -> None:
        self._sink.flush()

    @property
    def buffer(self) -> BinaryOutputTee:
        return self._buffer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sink, name)
