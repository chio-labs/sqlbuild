"""Fresh-process integration coverage for compile import boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    ExpectedBooleanTestCase,
    ExpectedCountTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    write_compile_startup_project,
)


@pytest.mark.parametrize(
    "test_case",
    [ExpectedCountTestCase(description="plain compile stays lazy", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_plain_compile_when_running_fresh_cli_then_optional_artifact_imports_stay_lazy(
    tmp_path: Path,
    test_case: ExpectedCountTestCase,
) -> None:
    write_compile_startup_project(tmp_path)
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
    "aggregate_models": "sqlbuild.cli.commands.models.runtime" in sys.modules,
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

    assert summary["models"] == test_case.expected_count
    assert json.loads(import_status_path.read_text(encoding="utf-8")) == {
        "aggregate_models": False,
        "dag": False,
        "manifest": False,
    }


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedBooleanTestCase(
            description="compatibility exports retain identity", expected_result=True
        )
    ],
    ids=lambda case: case.description,
)
def test_given_legacy_model_imports_when_loading_focused_models_then_exports_keep_identity(
    test_case: ExpectedBooleanTestCase,
) -> None:
    script = """
import json
from sqlbuild.cli.commands import models
from sqlbuild.cli.compile import models as compile_models
from sqlbuild.cli.entry import models as entry_models
from sqlbuild.cli.output import models as output_models

expected_modules = {
    "CompileAnalysis": compile_models,
    "CompileCommandRequest": compile_models,
    "CompileProfileFlags": compile_models,
    "CompileWriteResult": compile_models,
    "SqlTestArtifactCacheRecord": compile_models,
    "SqlTestArtifactIdentityContext": compile_models,
    "CliEntrypointHandlers": entry_models,
    "ParsedCliInvocation": entry_models,
    "SelectorFileSummary": entry_models,
    "SelectorInputs": entry_models,
    "SkillInstallTarget": output_models,
    "SkillMaintenanceResult": output_models,
    "SkillSettings": output_models,
    "SkillUpdateResult": output_models,
    "WrittenTarget": output_models,
}
print(json.dumps({
    name: getattr(models, name) is getattr(module, name)
    for name, module in expected_modules.items()
}))
"""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert all(json.loads(result.stdout).values()) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [ExpectedCountTestCase(description="dag command remains available", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_project_when_running_unaffected_dag_after_model_split_then_json_command_still_succeeds(
    tmp_path: Path,
    test_case: ExpectedCountTestCase,
) -> None:
    write_compile_startup_project(tmp_path)
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

    assert len(nodes) == test_case.expected_count
    assert [node["name"] for node in nodes] == ["orders"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-vv"])
