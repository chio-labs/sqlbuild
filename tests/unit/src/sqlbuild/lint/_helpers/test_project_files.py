"""Unit tests for collecting authored SQL files for lint runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint._helpers.project_files import collect_project_files
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult
from tests.unit.src.sqlbuild.lint._helpers._test_types import CollectProjectFilesTestCase
from tests.unit.src.sqlbuild.lint._helpers.helpers import write_orders_lint_project


@pytest.mark.parametrize(
    "test_case",
    [
        CollectProjectFilesTestCase(
            description="identical text shares the discovered string",
            model_bytes=b"MODEL (materialized table);\nSELECT 1 AS order_id\n",
            expected_shared=True,
        ),
        CollectProjectFilesTestCase(
            description="carriage returns keep the exact authored text",
            model_bytes=b"MODEL (materialized table);\r\nSELECT 1 AS order_id\r\n",
            expected_shared=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_discovered_project_when_collecting_files_then_returns_exact_authored_text(
    test_case: CollectProjectFilesTestCase, tmp_path: Path
) -> None:
    model_path: Path = write_orders_lint_project(
        project_dir=tmp_path, model_bytes=test_case.model_bytes
    )
    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    discovered: dict[Path, str] = {item.file_path: item.contents for item in inputs.model_files}

    files: dict[Path, str] = collect_project_files(project_dir=tmp_path, discovered_inputs=inputs)
    shared: LintRunResult = run_lint(
        project_dir=tmp_path, config=LintConfig(), discovered_inputs=inputs
    )
    fresh: LintRunResult = run_lint(project_dir=tmp_path, config=LintConfig())

    assert files == collect_project_files(project_dir=tmp_path)
    assert files[model_path] == test_case.model_bytes.decode("utf-8")
    assert (files[model_path] is discovered[model_path]) is test_case.expected_shared
    assert shared.source_texts == fresh.source_texts
    assert shared.violations == fresh.violations
    assert shared.files_checked == fresh.files_checked == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
