"""Canonical resource identity for one SQL test case execution."""

from pathlib import Path


def sql_test_resource_id(
    *,
    test_name: str,
    source_path: Path | None,
    block_index: int | None,
    case_name: str | None,
) -> str:
    """Return the exact stable identity of one plain or parameterized SQL test."""

    if source_path is None or block_index is None or case_name is None:
        return f"sql_test:{test_name}"
    return f"sql_test:{source_path.as_posix()}:{block_index}:{case_name}"
