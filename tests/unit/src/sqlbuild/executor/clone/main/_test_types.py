from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloneStreamTestCase:
    description: str
    model_names: tuple[str, ...]
    origin_schema: str
    destination_schema: str
    expected_positions: tuple[tuple[int, int], ...]
    expected_destination_relations: tuple[str, ...]


@dataclass(frozen=True)
class PrephaseCauseAnnotationTestCase:
    description: str
    caused_by_names: tuple[str, ...]
    expected_annotation: str


@dataclass(frozen=True)
class PrephaseCloneItemRowTestCase:
    description: str
    action: str
    status: str
    expected_label: str
    expected_status: str
