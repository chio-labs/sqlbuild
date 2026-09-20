"""Fresh-process integration coverage for compile import boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast


def _write_project(project_dir: Path) -> None:
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    models_dir: Path = project_dir / "models"
    models_dir.mkdir()
    (models_dir / "orders.sql").write_text(
        "MODEL (materialized table);\nSELECT 1 AS order_id\n", encoding="utf-8"
    )


def test_given_plain_compile_when_running_fresh_cli_then_optional_artifact_imports_stay_lazy(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    import_status_path: Path = tmp_path / "import_status.json"
    script = """
import json
import sys
from pathlib import Path
from sqlbuild.cli.commands.main.entrypoint.entry import main

exit_code = main([
    "--project-dir", sys.argv[1], "--no-color", "compile", "--json", "--no-cache"
])
Path(sys.argv[2]).write_text(json.dumps({
    "dag": "sqlbuild.compiler.dag.main.build" in sys.modules,
    "manifest": "sqlbuild.compiler.manifest.main.build" in sys.modules,
}), encoding="utf-8")
raise SystemExit(exit_code)
"""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(import_status_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload: dict[str, object] = json.loads(result.stdout)
    summary: dict[str, object] = cast(dict[str, object], payload["summary"])

    assert summary["models"] == 1
    assert json.loads(import_status_path.read_text(encoding="utf-8")) == {
        "dag": False,
        "manifest": False,
    }


def test_given_project_when_running_dag_after_graph_split_then_json_command_still_succeeds(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)
    script = """
import sys
from sqlbuild.cli.commands.main.entrypoint.entry import main

raise SystemExit(main(["--project-dir", sys.argv[1], "--no-color", "dag", "--json"]))
"""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload: dict[str, object] = json.loads(result.stdout)
    nodes: list[dict[str, object]] = cast(list[dict[str, object]], payload["nodes"])

    assert [node["name"] for node in nodes] == ["orders"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-vv"])
