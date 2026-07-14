"""Adapt a project for dbt SQL tests."""

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.helpers.selection.sql_test_targets import (
    adapt_project_for_dbt_sql_tests as _adapt,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def adapt_project_for_dbt_sql_tests(
    *, project: CompiledProject, manifest: DbtManifestIndex, target_names: tuple[str, ...]
) -> CompiledProject:
    """Expose selected dbt models as SQL test targets."""

    return _adapt(project=project, manifest=manifest, target_names=target_names)
