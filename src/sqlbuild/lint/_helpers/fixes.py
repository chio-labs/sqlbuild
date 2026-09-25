"""Deterministic lint edit planning, validation, and atomic persistence."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomically(*, path: Path, contents: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path: Path = Path(temporary_name)
    try:
        os.fchmod(descriptor, path.stat().st_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            _ = handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
