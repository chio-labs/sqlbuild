from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.commands.main.helpers.debug.models import DebugResult


@dataclass(frozen=True)
class DebugOutputTestCase:
    description: str
    result: DebugResult
    expected_text: str
    expected_json_fragment: str
    expected_color_fragments: tuple[str, ...] = ()
