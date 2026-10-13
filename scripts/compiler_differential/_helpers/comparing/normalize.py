"""Remove run-specific noise from compile outputs."""

from __future__ import annotations

from scripts.compiler_differential.constants import ELAPSED_TIME_MASK, ELAPSED_TIME_PATTERN
from sqlbuild._native import mask_capture_noise


def normalize_artifact_text(text: str) -> str:
    """Mask invocation ids and native store suffixes, which differ by design."""

    return mask_capture_noise(text)


def normalize_stderr(text: str) -> str:
    """Mask elapsed times as well as the artifact noise in progress and diagnostic output."""

    return ELAPSED_TIME_PATTERN.sub(ELAPSED_TIME_MASK, normalize_artifact_text(text))
