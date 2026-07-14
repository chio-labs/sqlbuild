"""Test helpers for seed executor tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import SeedPlanEntry
from sqlbuild.spec.contracts.models import SeedCsvSettings


def build_seed_plan_entry(*, seed_name: str, file_path: Path) -> SeedPlanEntry:
    return SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=seed_name),
        name=seed_name,
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name=seed_name,
            qualified_name=f"main.{seed_name}",
        ),
        file_path=file_path,
        columns=(ColumnInfo(name="id", type="INTEGER"),),
        csv_settings=SeedCsvSettings(),
        fingerprint_definition='{"seed":"missing"}',
        fingerprint_version_hash="expected-seed-version",
        fingerprint_metadata_json='{"seed":"missing"}',
    )
