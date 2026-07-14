"""Dagster resource for invoking the SQLBuild CLI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlbuild.integrations.dagster._helpers.dag import load_sqlbuild_dag
from sqlbuild.integrations.dagster._helpers.imports import load_dagster
from sqlbuild.integrations.dagster._helpers.invocation import (
    SqlBuildCliInvocation,
    start_sqlbuild_cli_invocation,
)
from sqlbuild.integrations.dagster.models import SqlBuildProject


class SqlBuildCliResource(load_dagster().ConfigurableResource):  # type: ignore[misc]
    """Dagster resource that shells out to the SQLBuild CLI."""

    project_dir: str = "."
    sqb_command: list[str] = ["sqb"]
    dag_path: str | None = None

    def __init__(
        self,
        project_dir: str | Path | SqlBuildProject = ".",
        sqb_command: list[str] | None = None,
        dag_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(project_dir, SqlBuildProject):
            project: SqlBuildProject = project_dir
            if sqb_command is None:
                sqb_command = list(project.sqb_command)
            if dag_path is None:
                dag_path = project.dag_path
            project_dir = project.project_dir
        super().__init__(
            project_dir=str(project_dir),
            sqb_command=sqb_command or ["sqb"],
            dag_path=None if dag_path is None else str(dag_path),
            **kwargs,
        )

    def cli(
        self,
        args: Sequence[str],
        *,
        context: Any = None,
        raise_on_error: bool = True,
    ) -> SqlBuildCliInvocation:
        """Create a SQLBuild CLI invocation for the provided command arguments."""

        loaded_dag: Mapping[str, Any] | None = None
        if self.dag_path is not None:
            loaded_dag = load_sqlbuild_dag(self.dag_path)
        return start_sqlbuild_cli_invocation(
            sqb_command=self.sqb_command,
            args=args,
            project_dir=Path(self.project_dir),
            raise_on_error=raise_on_error,
            context=context,
            dag=loaded_dag,
        )
