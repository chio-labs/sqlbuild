"""Standard output streams the CLI can always write, whatever the console code page."""

import codecs
import io
import sys

from sqlbuild.cli.entry.constants import OUTPUT_STREAM_ENCODING, OUTPUT_STREAM_ERRORS


def use_utf8_output_streams() -> tuple[bool, ...]:
    """Write stdout and stderr as UTF-8 when opened with another encoding; return which changed."""

    return tuple(use_utf8_stream(stream) for stream in (sys.stdout, sys.stderr))


def use_utf8_stream(stream: object) -> bool:
    """Reconfigure a text stream that is not UTF-8 to UTF-8; return whether it changed."""

    if not isinstance(stream, io.TextIOWrapper):
        return False
    if codecs.lookup(stream.encoding).name == codecs.lookup(OUTPUT_STREAM_ENCODING).name:
        return False
    stream.reconfigure(encoding=OUTPUT_STREAM_ENCODING, errors=OUTPUT_STREAM_ERRORS)
    return True
