from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagsterAssetSpecTestCase:
    description: str
    expected_asset_keys: tuple[tuple[str, ...], ...]
    expected_model_deps: tuple[tuple[str, ...], ...]
    expected_check_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterDecoratorTestCase:
    description: str
    expected_asset_keys: tuple[tuple[str, ...], ...]
