from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSqlTestGlueCliTestCase:
    """A DuckDB project whose SQL tests every engine must compile, inspect and run alike."""

    description: str
    files: dict[str, str]
    expected_compile_returncode: int
    expected_test_returncode: int
    expected_fragments: tuple[str, ...]
