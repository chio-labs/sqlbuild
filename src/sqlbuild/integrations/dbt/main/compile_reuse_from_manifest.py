"""Public dbt reuse_from manifest compile entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.helpers.reuse_from import compile_reuse_from_manifest
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtReuseFromCompileResult
from sqlbuild.spec.models.project import DbtReuseFromConfig


def compile_reuse_from_dbt_manifest(
    *,
    sqlbuild_project_dir: Path,
    dbt_options: DbtCliOptions,
    reuse_from: DbtReuseFromConfig,
    runner: DbtRunner,
) -> DbtReuseFromCompileResult:
    """Compile the reuse_from dbt git ref and return its manifest contents."""

    return compile_reuse_from_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=dbt_options,
        reuse_from=reuse_from,
        runner=runner,
    )
