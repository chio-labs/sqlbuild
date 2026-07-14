from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models.core import CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtCommandResult
from tests.integration.src.sqlbuild.integrations.dbt._test_types import (
    RealDbtManifestCompileTestCase,
    RealDbtSeedContentIdentityTestCase,
)
from tests.integration.src.sqlbuild.integrations.dbt.helpers import (
    build_external_sql_reference_resolver,
)

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtManifestCompileTestCase(
            description="validates and preserves SQLBuild dbt ref from real dbt manifest",
            sqlbuild_model_sql='MODEL ();\n\nselect order_id from __dbt_ref("stg_orders")\n',
            expected_compiled_sql='select order_id from __dbt_ref("stg_orders")',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_real_dbt_manifest_when_compiling_sqlbuild_then_preserves_dbt_ref(
    test_case: RealDbtManifestCompileTestCase,
    real_dbt_executable: str,
    dbt_project_dir: Path,
    dbt_profiles_dir: Path,
    tmp_path: Path,
) -> None:
    options: DbtCliOptions = DbtCliOptions(
        project_dir=dbt_project_dir,
        profiles_dir=dbt_profiles_dir,
        target_path=dbt_project_dir / "target",
    )
    compile_result: DbtCommandResult = DbtRunner(dbt_executable=real_dbt_executable).compile(
        options=options
    )
    assert compile_result.returncode == 0, compile_result.stderr or compile_result.stdout

    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    sqlbuild_project_dir.joinpath("models").mkdir(parents=True)
    sqlbuild_project_dir.joinpath("target").mkdir()
    sqlbuild_project_dir.joinpath("sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    sqlbuild_project_dir.joinpath("models/downstream_orders.sql").write_text(
        test_case.sqlbuild_model_sql, encoding="utf-8"
    )
    sqlbuild_project_dir.joinpath("target/manifest.json").write_text(
        dbt_project_dir.joinpath("target/manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    manifest_source: Path = dbt_project_dir / "target/manifest.json"
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=sqlbuild_project_dir
    )
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered_inputs,
        external_sql_reference_resolver=build_external_sql_reference_resolver(
            manifest_source=manifest_source
        ),
    )

    assert compile_inputs.model_inputs[0].query_sql == test_case.expected_compiled_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtSeedContentIdentityTestCase(
            description="independent content hash detects a seed edit dbt checksum misses",
            initial_seed_csv="id,name\n1,a\n2,b\n",
            mutated_seed_csv="id,name\n1,a\n2,c\n",
            expected_identity_changes=True,
        ),
        RealDbtSeedContentIdentityTestCase(
            description="newline-only seed edit does not change identity",
            initial_seed_csv="id,name\n1,a\n2,b\n",
            mutated_seed_csv="id,name\r\n1,a\r\n2,b",
            expected_identity_changes=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stale_dbt_checksum_when_indexing_then_independent_hash_isolates_seed_change(
    test_case: RealDbtSeedContentIdentityTestCase,
    real_dbt_executable: str,
    dbt_project_dir: Path,
    dbt_profiles_dir: Path,
) -> None:
    seeds_dir: Path = dbt_project_dir / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    seed_file: Path = seeds_dir / "raw_items.csv"
    seed_file.write_text(test_case.initial_seed_csv, encoding="utf-8")

    options: DbtCliOptions = DbtCliOptions(
        project_dir=dbt_project_dir,
        profiles_dir=dbt_profiles_dir,
        target_path=dbt_project_dir / "target",
    )
    compile_result: DbtCommandResult = DbtRunner(dbt_executable=real_dbt_executable).compile(
        options=options
    )
    assert compile_result.returncode == 0, compile_result.stderr or compile_result.stdout

    manifest_path: Path = dbt_project_dir / "target/manifest.json"
    manifest_data: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))

    initial_index: DbtManifestIndex = build_dbt_manifest_index(raw_data=manifest_data)
    seed_unique_ids: list[str] = list(initial_index.seeds_by_unique_id)
    assert len(seed_unique_ids) == 1
    seed_unique_id: str = seed_unique_ids[0]
    initial_identity: str | None = initial_index.seeds_by_unique_id[seed_unique_id].identity_hash

    # Mutate the on-disk seed but reuse the SAME compiled manifest (frozen dbt checksum),
    # simulating dbt failing to update its checksum for a real content change.
    seed_file.write_text(test_case.mutated_seed_csv, encoding="utf-8")
    mutated_index: DbtManifestIndex = build_dbt_manifest_index(raw_data=manifest_data)
    mutated_identity: str | None = mutated_index.seeds_by_unique_id[seed_unique_id].identity_hash

    assert initial_identity is not None
    assert mutated_identity is not None
    assert (initial_identity != mutated_identity) is test_case.expected_identity_changes
