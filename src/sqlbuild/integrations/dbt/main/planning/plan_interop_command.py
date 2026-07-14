"""Plan a dbt interop command."""

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt._helpers.planning.orchestration import (
    plan_dbt_interop_command as _plan,
)
from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtInteropCommandArgs,
    DbtInteropPlan,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def plan_dbt_interop_command(
    *,
    command: DbtInteropCommand | str,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    dbt_runner: DbtRunner,
    dbt_options: DbtCliOptions,
    command_args: DbtInteropCommandArgs,
) -> DbtInteropPlan:
    """Plan dbt and SQLBuild work from compiled inputs."""

    return _plan(
        command=command,
        project=project,
        manifest=manifest,
        graph=graph,
        dbt_runner=dbt_runner,
        dbt_options=dbt_options,
        command_args=command_args,
    )
