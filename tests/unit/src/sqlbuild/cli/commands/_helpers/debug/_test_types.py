from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DebugWarehouseVarsTestCase:
    description: str
    project_contents: str
    cli_vars: dict[str, object]
    expected_lines: tuple[tuple[str, str, str], ...]
