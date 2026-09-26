"""Compiler Rules end-to-end fixture helpers."""

import subprocess
import sys
from pathlib import Path

from scripts.rules_benchmark._helpers.custom_rules import write_custom_rules

__all__ = ("write_custom_rules",)


def write_unevaluated_rules_project(
    *,
    project_dir: Path,
    model_options: str = "",
    configuration: str = "",
    adapter: str = "duckdb",
    resource_path: str = "models/staging/orders.sql",
    resource_template: str = "MODEL ({options});\nSELECT {expression} AS order_id",
) -> None:
    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "{adapter}"\n[rules]\nselect = ["SQBRSQL035"]\n'
        + configuration
    )
    models: Path = project_dir / "models/staging"
    models.mkdir(parents=True)
    (models / "orders.sql").write_text("MODEL ();\nSELECT 1 AS order_id\n")
    resource: Path = project_dir / resource_path
    resource.parent.mkdir(parents=True, exist_ok=True)
    resource.write_text(
        resource_template.format(options=model_options, expression="ABS(" * 130 + "1" + ")" * 130)
    )


def run_unevaluated_rules_cli(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--no-color",
            "--project-dir",
            str(project_dir),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
