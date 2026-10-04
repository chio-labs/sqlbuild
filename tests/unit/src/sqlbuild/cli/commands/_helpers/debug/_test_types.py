from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.commands.models import DebugResult


@dataclass(frozen=True)
class DebugOutputTestCase:
    description: str
    result: DebugResult
    expected_text: str
    expected_json_fragment: str
    expected_color_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DebugWarehouseVarsTestCase:
    description: str
    project_contents: str
    cli_vars: dict[str, object]
    expected_lines: tuple[tuple[str, str, str], ...]
