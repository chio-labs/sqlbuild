"""Compare two stage captures on disk without loading either one whole."""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.compare import (
    first_json_difference,
    preview,
)
from scripts.compiler_differential._helpers.comparing.normalize import normalize_artifact_text
from scripts.compiler_differential.classes.capture_file import CaptureFile
from scripts.compiler_differential.constants import MISSING_VALUE
from scripts.compiler_differential.models import Divergence


def first_capture_difference(
    *, left: Path, right: Path, ignored: frozenset[str] = frozenset()
) -> Divergence | None:
    """Return the first JSON pointer outside `ignored`, or line for invalid JSON, that differs."""

    try:
        left_capture: CaptureFile = CaptureFile(left)
        right_capture: CaptureFile = CaptureFile(right)
        return first_json_difference(
            left=left_capture.root,
            right=right_capture.root,
            resolve=(left_capture.resolve, right_capture.resolve),
            ignored=ignored,
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _first_line_difference(left=left, right=right)


def _first_line_difference(*, left: Path, right: Path) -> Divergence | None:
    with left.open("rb") as left_stream, right.open("rb") as right_stream:
        lines: Iterator[tuple[bytes | None, bytes | None]] = itertools.zip_longest(
            left_stream, right_stream
        )
        for number, (left_line, right_line) in enumerate(lines, start=1):
            left_text: str = _line_text(left_line)
            right_text: str = _line_text(right_line)
            if left_text != right_text:
                return Divergence(
                    location=f"line {number}", left=preview(left_text), right=preview(right_text)
                )
    return None


def _line_text(line: bytes | None) -> str:
    if line is None:
        return MISSING_VALUE
    return normalize_artifact_text(line.decode("utf-8", "surrogateescape").rstrip("\n"))
