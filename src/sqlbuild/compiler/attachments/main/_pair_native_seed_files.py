"""Pair seed declarations with seed CSV files natively for the preview compiler engine."""

from __future__ import annotations

import sqlbuild._native as _native


def pair_native_seed_files(
    *, declaration_names: list[str], file_stems: list[str]
) -> tuple[list[int], None] | tuple[None, int]:
    """Return each declaration's seed file index, or the index of the first one without a file."""

    return _native.pair_seed_files(declaration_names, file_stems)
