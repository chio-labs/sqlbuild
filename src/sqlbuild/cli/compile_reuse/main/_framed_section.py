"""Public entry for framing one stored section with its length and checksum."""

from __future__ import annotations

from sqlbuild.cli.compile_reuse._helpers.entry_file import framed_section


def framed_stored_section(*, data: bytes) -> bytes:
    """Prefix one section with its length and checksum so a reader can verify it."""

    return framed_section(data=data)
