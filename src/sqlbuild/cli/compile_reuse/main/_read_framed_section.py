"""Public entry for reading one framed stored section."""

from __future__ import annotations

from typing import BinaryIO

from sqlbuild.cli.compile_reuse._helpers.entry_file import read_framed_section


def read_stored_section(*, handle: BinaryIO) -> bytes:
    """Read one length- and checksum-framed section, raising when it is damaged."""

    return read_framed_section(handle=handle)
