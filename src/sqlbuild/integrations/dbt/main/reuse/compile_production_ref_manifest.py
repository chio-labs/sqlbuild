"""Public dbt production ref manifest compile entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.reuse.production_ref import compile_production_ref_manifest
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtProductionRefCompileResult
from sqlbuild.spec.contracts.models import DbtProductionRefConfig


def compile_production_ref_dbt_manifest(
    *,
    sqlbuild_project_dir: Path,
    dbt_options: DbtCliOptions,
    production_ref: DbtProductionRefConfig,
    runner: DbtRunner,
) -> DbtProductionRefCompileResult:
    """Compile the production_ref dbt git ref and return its manifest contents."""

    return compile_production_ref_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=dbt_options,
        production_ref=production_ref,
        runner=runner,
    )
