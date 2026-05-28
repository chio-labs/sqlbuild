"""Rivers integration runtime models."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.integrations.rivers.exceptions import RiversProjectPrepareError


@dataclass(frozen=True)
class SqlBuildProject:
    """SQLBuild project paths and artifact preparation settings."""

    project_dir: Path
    target_path: Path = Path("target")
    dag_filename: str = "sqlbuild_dag.json"
    sqb_command: Sequence[str] = ("sqb",)
    prepare_project_cli_args: Sequence[str] = ("compile", "--dag")

    @property
    def dag_path(self) -> Path:
        """Return the SQLBuild DAG artifact path for this project."""

        return self.project_dir / self.target_path / self.dag_filename

    def prepare(self) -> None:
        """Generate the SQLBuild DAG artifact by invoking SQLBuild."""

        command: tuple[str, ...] = (
            *tuple(self.sqb_command),
            *tuple(self.prepare_project_cli_args),
            str(self.dag_path),
        )
        self.dag_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            completed: subprocess.CompletedProcess[str]
            completed = subprocess.run(
                command,
                cwd=self.project_dir,
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as error:
            raise RiversProjectPrepareError(
                f"could not run SQLBuild DAG preparation command: {' '.join(command)}"
            ) from error
        if completed.returncode != 0:
            raise RiversProjectPrepareError(
                "SQLBuild DAG preparation failed with exit code "
                f"{completed.returncode}: {' '.join(command)}\n{completed.stderr}"
            )
        if not self.dag_path.exists():
            raise RiversProjectPrepareError(
                f"did not find SQLBuild DAG artifact at expected path {self.dag_path}"
            )

    def prepare_if_dev(self) -> None:
        """Generate the DAG artifact when running under Rivers local development."""

        if os.getenv("RIVERS_DEPLOYMENT") == "dev":
            self.prepare()
