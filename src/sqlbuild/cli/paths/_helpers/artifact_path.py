"""Stable, filesystem-safe CLI artifact paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlbuild.compiler.planner.models import SqlTestPlanEntry

_CHAIN_DIR: str = "_chain_"
_SQL_FILE_SUFFIX: str = ".sql"
_MAX_CHAIN_COMPONENT_BYTES: int = 200
_CHAIN_DIGEST_LENGTH: int = 12
_CHAIN_EDGE_NAME_BYTES: int = 80


def build_sql_test_output_path(entry: SqlTestPlanEntry) -> Path:
    """Return a readable test path with bounded chain directory components."""

    return build_sql_test_output_path_from_values(
        name=entry.name,
        source_path=entry.source_path,
        block_index=entry.block_index,
        case_name=entry.case_name,
        model_names=tuple(step.model_name for step in entry.chain),
    )


def build_sql_test_output_path_from_values(
    *,
    name: str,
    source_path: Path | None,
    block_index: int | None,
    case_name: str | None,
    model_names: tuple[str, ...],
) -> Path:
    """Return the stable test path from compact planner artifact metadata."""

    if case_name is None or source_path is None:
        return _test_folder_from_names(name=name, model_names=model_names) / (
            f"{name}{_SQL_FILE_SUFFIX}"
        )
    source_stem: Path = source_path.with_suffix("")
    return source_stem / f"block_{block_index}__{case_name}{_SQL_FILE_SUFFIX}"


def _test_folder_from_names(*, name: str, model_names: tuple[str, ...]) -> Path:
    unique_names: list[str] = sorted(set(model_names))
    if len(unique_names) <= 1:
        return Path(unique_names[0] if unique_names else name)
    chain_name: str = "__".join(unique_names)
    if len(chain_name.encode()) <= _MAX_CHAIN_COMPONENT_BYTES:
        return Path(_CHAIN_DIR) / chain_name
    digest: str = hashlib.sha256(chain_name.encode()).hexdigest()[:_CHAIN_DIGEST_LENGTH]
    first_name: str = _truncate_utf8(value=unique_names[0], max_bytes=_CHAIN_EDGE_NAME_BYTES)
    last_name: str = _truncate_utf8(value=unique_names[-1], max_bytes=_CHAIN_EDGE_NAME_BYTES)
    return Path(_CHAIN_DIR) / f"{first_name}__{last_name}__{digest}"


def _truncate_utf8(*, value: str, max_bytes: int) -> str:
    return value.encode()[:max_bytes].decode(errors="ignore")
