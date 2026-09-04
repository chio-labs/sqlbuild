from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiversConstantGuardTestCase:
    description: str
    expected_exhaustive: bool


@dataclass(frozen=True)
class RiversPythonArtifactCompatibilityTestCase:
    description: str
    expected_asset_names: tuple[str, ...]
    expected_order_deps: tuple[str, ...]
    expected_task_deps: tuple[str, ...]
    expected_asset_deps: tuple[str, ...]
    expected_task_kinds: list[str]
    expected_asset_kinds: list[str]
    expected_task_group: str
    expected_asset_group: str
    expected_asset_metadata_keys: tuple[str, ...]
