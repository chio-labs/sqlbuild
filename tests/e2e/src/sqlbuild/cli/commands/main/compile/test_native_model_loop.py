"""The preview engine's native model loop compiles exactly as the Python engine does."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeModelLoopParityTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    copy_compile_project,
    prepare_compile_reuse_project,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
)

_DECLARATIONS: dict[str, str] = {
    "enums/order_status.sql": "ENUM (name order_status, members [PLACED, SHIPPED]);\n",
    "constants/limits.sql": "CONSTANT (name order_cap, value 3);\n",
}
_MARTS_DECLARATIONS: dict[str, str] = {
    "models/marts/_sqlbuild/_enums/order_status.sql": (
        "ENUM (name order_status, members [PLACED, SHIPPED]);\n"
    ),
    "models/marts/_sqlbuild/_constants/limits.sql": "CONSTANT (name order_cap, value 3);\n",
}
_DECLARATION_MODEL: str = """MODEL (materialized view, description "Order flags.");

SELECT
  order_id,
  @enum("order_status").PLACED AS placed_status,
  @const("order_cap") AS order_cap,
  '@const("order_cap")' AS literal_text
FROM __ref("stg_orders")
"""


@pytest.mark.parametrize(
    "test_case",
    [
        NativeModelLoopParityTestCase(
            description="folder_private_declaration_references",
            project_files={
                **_MARTS_DECLARATIONS,
                "models/marts/order_flags.sql": _DECLARATION_MODEL,
            },
            engines=("python", "native-preview"),
            expected_exit_codes=(0, 0),
            expected_report_text="order_flags",
        ),
        NativeModelLoopParityTestCase(
            description="python_identity_error_for_a_folder_containing_a_colon",
            project_files={**_DECLARATIONS, "models/a:b/order_flags.sql": _DECLARATION_MODEL},
            engines=("python", "native-preview"),
            expected_exit_codes=(1, 1),
            expected_report_text="Unknown qualified identity kind",
        ),
        NativeModelLoopParityTestCase(
            description="rejected_reference_call_beside_declaration_references",
            project_files={
                **_MARTS_DECLARATIONS,
                "models/marts/order_flags.sql": _DECLARATION_MODEL.replace(
                    '__ref("stg_orders")', "__ref('stg_orders')"
                ),
            },
            engines=("python", "native-preview"),
            expected_exit_codes=(1, 1),
            expected_report_text="P012",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_declarations_when_compiling_with_preview_then_output_matches_python(
    test_case: NativeModelLoopParityTestCase, tmp_path: Path
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    for relative_path, contents in test_case.project_files.items():
        write_project_file(prepared_project, relative_path, contents)
    runs: list[CompileReuseRun] = [
        run_reuse_compile(
            project_dir=copy_compile_project(
                source=prepared_project, destination=tmp_path / engine
            ),
            env={},
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
