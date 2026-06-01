from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiversPythonArtifactCompatibilityTestCase:
    description: str
    expected_asset_names: tuple[str, ...]
    expected_order_deps: tuple[str, ...]
