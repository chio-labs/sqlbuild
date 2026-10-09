"""Native model config in the default engine compiles exactly as the Python engine does."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeModelConfigParityTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    copy_compile_project,
    prepare_compile_reuse_project,
    replace_project_text,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
)

_ORDER_QUALITY_MODEL: str = """MODEL (
  materialized table,
  description "Order quality checks.",
  schema "${coalesce(ENV:SQB_ORDER_QUALITY_SCHEMA, 'quality')}_${CTX:run.target}",
  tags ["${if(eq(CTX:run.target, 'dev'), 'development', 'release')}"],
  audits [
    expression_is_true (
      name "quantity_is_positive",
      expression "quantity > 0",
      severity error,
    ),
  ],
  columns (
    order_id (
      type INTEGER,
      nullable false,
      description "Order key",
      audits [not_null (severity error, name order_id_present), unique],
    ),
    status (
      type VARCHAR,
      audits [
        accepted_values (
          values ["placed", "preparing", "ready", "completed", "cancelled"],
          severity warn,
          description "Known statuses",
          always_run true,
        ),
      ],
    ),
    Quantity (type INTEGER, description "Waffles ordered"),
  ),
);

SELECT order_id, status, quantity AS Quantity
FROM __ref("stg_orders")
"""
_INVALID_SEVERITY_MODEL: str = """MODEL (
  materialized table,
  columns (
    order_id (audits [not_null (severity fatal)]),
  ),
);

SELECT order_id FROM __ref("stg_orders")
"""
_TARGET_SCHEMA: tuple[str, str] = (
    'schema = "dev"',
    "schema = \"${coalesce(ENV:SQB_TARGET_SCHEMA, ENV:SQB_MISSING_SCHEMA, 'dev')}\"",
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeModelConfigParityTestCase(
            description="header_metadata_and_templates",
            project_files={"models/marts/order_quality.sql": _ORDER_QUALITY_MODEL},
            project_config_replacements=(_TARGET_SCHEMA,),
            environment={"SQB_TARGET_SCHEMA": "analytics"},
            engines=("python", "native"),
            expected_exit_codes=(0, 0),
            expected_report_text="order_quality",
        ),
        NativeModelConfigParityTestCase(
            description="python_error_for_an_invalid_audit_severity",
            project_files={"models/marts/order_quality.sql": _INVALID_SEVERITY_MODEL},
            project_config_replacements=(),
            environment={},
            engines=("python", "native"),
            expected_exit_codes=(1, 1),
            expected_report_text="severity",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_model_config_when_compiling_natively_then_output_matches_python(
    test_case: NativeModelConfigParityTestCase, tmp_path: Path
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    for relative_path, contents in test_case.project_files.items():
        write_project_file(prepared_project, relative_path, contents)
    for old, new in test_case.project_config_replacements:
        replace_project_text(prepared_project, "sqlbuild_project.toml", old, new)
    runs: list[CompileReuseRun] = [
        run_reuse_compile(
            project_dir=copy_compile_project(
                source=prepared_project, destination=tmp_path / engine
            ),
            env=test_case.environment,
            global_args=("--compiler-engine", engine),
        )
        for engine in test_case.engines
    ]

    assert tuple(run.returncode for run in runs) == test_case.expected_exit_codes
    assert report_without_engine(runs[1]) == report_without_engine(runs[0])
    assert stderr_without_durations(stderr=runs[1].stderr) == stderr_without_durations(
        stderr=runs[0].stderr
    )
    assert runs[1].compiled == runs[0].compiled
    assert test_case.expected_report_text in runs[0].report + runs[0].stderr


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
