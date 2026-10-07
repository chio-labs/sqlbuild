"""E2E tests for reference calls that compile could never replace with a relation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    RejectedReferenceCallTestCase,
    ReplaceableReferenceCallTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    prepare_reference_call_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
_CANONICAL_SOURCE: str = '__source("raw_orders")'
_CANONICAL_REF: str = '__ref("stg_orders")'


@pytest.mark.parametrize(
    "test_case",
    [
        ReplaceableReferenceCallTestCase(
            description="python engine builds double quoted references",
            engine="python",
            expected_total_cents="2850",
        ),
        ReplaceableReferenceCallTestCase(
            description="native engine builds double quoted references",
            engine="native",
            expected_total_cents="2850",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_double_quoted_reference_calls_when_building_then_relations_resolve(
    test_case: ReplaceableReferenceCallTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_reference_call_project(
        tmp_path=tmp_path, staging_from=_CANONICAL_SOURCE, mart_from=_CANONICAL_REF
    )

    built: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("build",), env={_ENGINE_ENV_VAR: test_case.engine}
    )
    totals: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir,
        command=("query", "SELECT total_cents FROM main.order_totals", "--json"),
    )

    assert built.returncode == 0, built.stdout + built.stderr
    assert totals.returncode == 0, totals.stdout + totals.stderr
    assert test_case.expected_total_cents in totals.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        RejectedReferenceCallTestCase(
            description="python engine rejects unquoted ref name",
            engine="python",
            staging_from=_CANONICAL_SOURCE,
            mart_from="__ref(stg_orders)",
            expected_code="P012",
            expected_message="__ref(stg_orders) is not a valid __ref() call",
            expected_corrected_call='__ref("stg_orders")',
        ),
        RejectedReferenceCallTestCase(
            description="python engine rejects comment inside ref call",
            engine="python",
            staging_from=_CANONICAL_SOURCE,
            mart_from="__ref( /* upstream */ 'stg_orders')",
            expected_code="P012",
            expected_message="__ref( /* upstream */ 'stg_orders') is not a valid __ref() call",
            expected_corrected_call='__ref("stg_orders")',
        ),
        RejectedReferenceCallTestCase(
            description="python engine rejects single quoted source name",
            engine="python",
            staging_from="__source('raw_orders')",
            mart_from=_CANONICAL_REF,
            expected_code="P012",
            expected_message="__source('raw_orders') is not a valid __source() call",
            expected_corrected_call='__source("raw_orders")',
        ),
        RejectedReferenceCallTestCase(
            description="native engine rejects unquoted ref name",
            engine="native",
            staging_from=_CANONICAL_SOURCE,
            mart_from="__ref(stg_orders)",
            expected_code="P012",
            expected_message="__ref(stg_orders) is not a valid __ref() call",
            expected_corrected_call='__ref("stg_orders")',
        ),
        RejectedReferenceCallTestCase(
            description="native engine rejects comment inside ref call",
            engine="native",
            staging_from=_CANONICAL_SOURCE,
            mart_from="__ref( /* upstream */ 'stg_orders')",
            expected_code="P012",
            expected_message="__ref( /* upstream */ 'stg_orders') is not a valid __ref() call",
            expected_corrected_call='__ref("stg_orders")',
        ),
        RejectedReferenceCallTestCase(
            description="native engine rejects single quoted source name",
            engine="native",
            staging_from="__source('raw_orders')",
            mart_from=_CANONICAL_REF,
            expected_code="P012",
            expected_message="__source('raw_orders') is not a valid __source() call",
            expected_corrected_call='__source("raw_orders")',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_reference_call_compile_cannot_replace_when_building_then_fails_with_corrected_call(
    test_case: RejectedReferenceCallTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_reference_call_project(
        tmp_path=tmp_path, staging_from=test_case.staging_from, mart_from=test_case.mart_from
    )

    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir,
        command=("compile", "--json"),
        env={_ENGINE_ENV_VAR: test_case.engine},
    )
    built: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("build",), env={_ENGINE_ENV_VAR: test_case.engine}
    )

    diagnostics: list[dict[str, object]] = cast(
        list[dict[str, object]], json.loads(compiled.stdout)["diagnostics"]
    )
    assert compiled.returncode == 1, compiled.stdout + compiled.stderr
    assert built.returncode == 1, built.stdout + built.stderr
    assert {item["code"] for item in diagnostics} == {test_case.expected_code}
    assert diagnostics[0]["message"] == test_case.expected_message
    assert str(diagnostics[0]["help"]).endswith(test_case.expected_corrected_call)
    assert f"error[{test_case.expected_code}]" in built.stdout + built.stderr
