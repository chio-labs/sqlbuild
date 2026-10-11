"""Interpreter and site-path inputs that must remain unchanged before skipping Python startup."""

import site
import sys
from os import stat_result
from pathlib import Path


def startup_inputs() -> list[tuple[str, int | None, int | None]]:
    """Stamp startup directories, path files, interpreter and virtual-environment configuration."""

    directories: set[Path] = {
        Path(entry).absolute()
        for entry in (*sys.path, *site.getsitepackages(), site.getusersitepackages())
    }
    paths: set[Path] = {
        *directories,
        Path(sys.executable),
        Path(sys.prefix) / "pyvenv.cfg",
        Path(sys.base_prefix) / "pyvenv.cfg",
    }
    for directory in directories:
        paths.update(directory.glob("*.pth"))
    stamps: list[tuple[str, int | None, int | None]] = []
    for path in sorted(paths):
        try:
            status: stat_result = path.stat()
        except FileNotFoundError:
            stamps.append((str(path), None, None))
        else:
            stamps.append((str(path), status.st_mtime_ns, status.st_size))
    return stamps
