from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.executor.clone.types import CloneAction


@dataclass(frozen=True)
class CloneStreamTestCase:
    description: str
    model_names: tuple[str, ...]
    origin_schema: str
    destination_schema: str
    expected_positions: tuple[tuple[int, int], ...]
    expected_destination_relations: tuple[str, ...]


@dataclass(frozen=True)
class InterleavedCloneGraphTestCase:
    description: str
    expected_names: tuple[str, ...]
    expected_actions: tuple[CloneAction, ...]
    expected_function_statement: str
    expected_view_statement_fragment: str


@dataclass(frozen=True)
class PrephaseCloneItemRowTestCase:
    description: str
    action: str
    status: str
    expected_label: str
    expected_status: str
