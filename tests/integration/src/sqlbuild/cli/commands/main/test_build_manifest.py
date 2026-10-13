"""Integration coverage for the manifest a real build publishes."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import BuildManifestTestCase
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    run_build,
    write_test_planning_project,
)


@pytest.mark.parametrize(
    "test_case",
    (
        BuildManifestTestCase(
            description="planned models and SQL tests reach the build manifest",
            model_count=3,
            expected_test_type="sql_native",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_duckdb_project_when_building_with_manifest_then_plan_nodes_are_published(
    test_case: BuildManifestTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project: Path = tmp_path / "orders"
    write_test_planning_project(
        project_dir=project,
        model_count=test_case.model_count,
        rules_config=f'\n[connection]\ndatabase = "{project / "orders.duckdb"}"\n',
    )

    exit_code, output = run_build(project_dir=project, flags=("--manifest",), capsys=capsys)

    assert exit_code == 0, output
    contents: bytes = (project / "target" / "manifest.json").read_bytes()
    manifest: dict[str, Any] = json.loads(contents)
    assert contents.endswith(b"}\n")
    nodes: dict[str, Any] = manifest["nodes"]
    model_ids: list[str] = [
        f"model.orders.orders_{index:03}" for index in range(test_case.model_count)
    ]
    assert Counter(
        (node["resource_type"], node["meta"].get("sqlbuild_test_type")) for node in nodes.values()
    ) == {
        ("model", None): test_case.model_count,
        ("test", test_case.expected_test_type): test_case.model_count - 1,
    }
    assert nodes[model_ids[1]]["compiled_code"].startswith("SELECT")
    assert model_ids[0] in manifest["parent_map"][model_ids[1]]
    assert model_ids[1] in manifest["child_map"][model_ids[0]]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
