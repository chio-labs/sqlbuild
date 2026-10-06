"""Builders for stored compile artifact unit tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlbuild.cli.compile_reuse.constants import DIGEST_SIZE_BYTES

STORED_SQL: bytes = b"SELECT order_id FROM orders\n"


def artifact_unchanged(_path: Path) -> None:
    """Leave the stored artifact as it is."""


def artifact_rewritten(path: Path) -> None:
    """Rewrite the stored artifact with other contents."""

    path.write_bytes(b"SELECT order_id FROM returns\n")


def artifact_removed(path: Path) -> None:
    """Remove the stored artifact."""

    path.unlink()


def artifact_digest(contents: bytes) -> str:
    """Return the digest compile reuse records for artifact contents."""

    return hashlib.blake2b(contents, digest_size=DIGEST_SIZE_BYTES).hexdigest()
