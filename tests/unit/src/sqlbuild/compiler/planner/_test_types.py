from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy


@dataclass(frozen=True)
class MissingOriginBlockTestCase:
    description: str
    origin_tracked: bool
    policy: MissingMigrationOriginPolicy
    expected_blocks: bool
