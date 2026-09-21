"""Validate the fresh-process compile memory limit."""

import os
from pathlib import Path

from scripts.cold_compile_performance.constants import UNLIMITED_CGROUP_MEMORY_VALUE
from scripts.cold_compile_performance.exceptions import CgroupMemoryLimitError


def assert_required_cgroup_memory_limit() -> None:
    """Validate the configured cgroup-v2 memory limit when CI requires one."""

    raw_required_limit: str | None = os.environ.get("SQLBUILD_REQUIRE_MEMORY_LIMIT_BYTES")
    if raw_required_limit is None:
        return
    required_limit: int = int(raw_required_limit)
    actual_limit: int | None = _current_cgroup_memory_limit_bytes()
    if actual_limit != required_limit:
        raise CgroupMemoryLimitError(
            f"expected cgroup memory limit {required_limit}, found {actual_limit}"
        )


def _current_cgroup_memory_limit_bytes() -> int | None:
    cgroup_lines: list[str] = Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
    unified_entry: str | None = next(
        (line for line in cgroup_lines if line.startswith("0::")),
        None,
    )
    if unified_entry is None:
        return None
    relative_path: str = unified_entry.removeprefix("0::").lstrip("/")
    limit_path: Path = Path("/sys/fs/cgroup") / relative_path / "memory.max"
    if not limit_path.exists():
        return None
    raw_limit: str = limit_path.read_text(encoding="utf-8").strip()
    return None if raw_limit == UNLIMITED_CGROUP_MEMORY_VALUE else int(raw_limit)
