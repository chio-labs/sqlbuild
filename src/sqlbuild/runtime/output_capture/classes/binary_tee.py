"""Transparent binary stream tee for output capture."""

from __future__ import annotations

from typing import Any

from sqlbuild.runtime.output_capture.classes.dispatcher import OutputCaptureDispatcher
from sqlbuild.runtime.output_capture.types import CommandOutputStream


class BinaryOutputTee:
    """Preserve raw binary writes while forwarding accepted bytes to capture."""

    def __init__(
        self,
        *,
        sink: Any,
        dispatcher: OutputCaptureDispatcher,
        stream: CommandOutputStream,
        encoding: str,
        text_sink: bool,
    ) -> None:
        self._sink: Any = sink
        self._dispatcher: OutputCaptureDispatcher = dispatcher
        self._stream: CommandOutputStream = stream
        self._encoding: str = encoding
        self._text_sink: bool = text_sink

    def write(self, data: bytes | bytearray) -> int:
        offered: bytes = bytes(data)
        if self._text_sink:
            offered_text: str = offered.decode(self._encoding, "surrogateescape")
            result: object = self._sink.write(offered_text)
            accepted_text_count: int = result if isinstance(result, int) else len(offered_text)
            accepted: bytes = offered_text[:accepted_text_count].encode(
                self._encoding, "surrogateescape"
            )
        else:
            result = self._sink.write(offered)
            accepted_count: int = result if isinstance(result, int) else len(offered)
            accepted = offered[:accepted_count]
        try:
            self._dispatcher.append(
                stream=self._stream,
                text=accepted.decode(self._encoding, "surrogateescape"),
            )
        except BaseException:
            pass
        return len(accepted)

    def flush(self) -> None:
        self._sink.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sink, name)
