"""The preview engine reports model config, template and header errors as Python does."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

import sqlbuild.compiler.compile._helpers.attachment.core as attachment_core
import sqlbuild.compiler.compile._helpers.attachment.model_config as model_config
import sqlbuild.compiler.compile._helpers.render.context_templates as context_templates
from scripts.compiler_differential.constants import FAILURE_BASE_MART
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    MacroExpandedValidatorErrorTestCase,
    NativeConfigErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    fallback_free_preview_compile,
    python_engine_compile,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_counted_error_project,
)

_ENGINES: tuple[str, str] = ("python", "native-preview")
_CALL_LOG: str = "macro_calls.log"
_COUNTED_MACRO: str = (
    "from pathlib import Path\n\n\n"
    "def counted(expression: str) -> str:\n"
    '    """Return the expression, logging each execution."""\n\n'
    f"    with (Path(__file__).resolve().parents[1] / {_CALL_LOG!r}).open(\n"
    '        "a", encoding="utf-8"\n'
    "    ) as log:\n"
    '        _ = log.write("call\\n")\n'
    "    return expression\n"
)
_COUNTED_MART: str = FAILURE_BASE_MART.replace("SUM(amount)", "SUM(@counted('amount'))")
_UPSTREAM_MACRO: str = _COUNTED_MACRO.replace(
    "def counted(expression: str) -> str:", "def upstream() -> str:"
).replace("    return expression\n", "    return '__ref(\"ghost\")'\n")
_STAGING_PATH: str = "models/staging/stg_orders.sql"
_STAGING_BODY: str = (
    '\n);\n\nSELECT order_id, customer_id, amount, status\nFROM __source("raw_orders")\n'
)
_INCREMENTAL: str = (
    "  materialized incremental,\n  incremental_strategy append,\n  cursor order_id,\n"
    "  cursor_type integer,\n"
)
_FALLBACKS: tuple[tuple[ModuleType, str], ...] = (
    (model_config, "run_python_model_validators"),
    (model_config, "_parse_model_header_columns"),
    (model_config, "parse_audit_instances"),
    (attachment_core, "build_model_config"),
    (context_templates, "expand_template_data"),
)
_PROJECT_FILES: dict[str, str] = {
    "macros/counted.py": _COUNTED_MACRO,
    "models/marts/customer_totals.sql": _COUNTED_MART,
    _CALL_LOG: "",
}


@pytest.mark.parametrize(
    "test_case",
    [
        NativeConfigErrorTestCase(
            description="validator_error_after_a_macro_ran",
            project_files={
                _STAGING_PATH: "MODEL (\n  materialized incremental,\n  incremental_strategy upsert,"
                + _STAGING_BODY
            },
            expected_report_text="unknown incremental_strategy 'upsert'",
            expected_macro_calls=[1, 2],
            expected_python_fallbacks=[],
        ),
        NativeConfigErrorTestCase(
            description="first_of_several_validator_faults",
            project_files={
                _STAGING_PATH: "MODEL (\n"
                + _INCREMENTAL
                + "  cursor_start 20,\n  cursor_end 10,\n  contract strict,"
                + _STAGING_BODY
            },
            expected_report_text="cursor_start must be before exclusive cursor_end",
            expected_macro_calls=[1, 2],
            expected_python_fallbacks=[],
        ),
        NativeConfigErrorTestCase(
            description="template_error_after_a_macro_ran",
            project_files={
                _STAGING_PATH: 'MODEL (\n  schema "${missing_region}_core",' + _STAGING_BODY
            },
            expected_report_text="model config references unknown variable 'missing_region'",
            expected_macro_calls=[1, 1],
            expected_python_fallbacks=[],
        ),
        NativeConfigErrorTestCase(
            description="header_column_error_after_a_macro_ran",
            project_files={
                _STAGING_PATH: "MODEL (\n  columns (order_id (type INTEGER, format plain)),"
                + _STAGING_BODY
            },
            expected_report_text="column 'order_id' has unknown metadata keys: format",
            expected_macro_calls=[1, 1],
            expected_python_fallbacks=[],
        ),
        NativeConfigErrorTestCase(
            description="header_audit_error_after_a_macro_ran",
            project_files={
                _STAGING_PATH: "MODEL (\n  audits [unique_combination (columns [order_id], "
                "severity fatal)]," + _STAGING_BODY
            },
            expected_report_text="'severity' must be one of: warn, error",
            expected_macro_calls=[1, 1],
            expected_python_fallbacks=[],
        ),
        NativeConfigErrorTestCase(
            description="config_build_error_after_a_macro_ran",
            project_files={_STAGING_PATH: 'MODEL (\n  tags "orders",' + _STAGING_BODY},
            expected_report_text="tags must be a list",
            expected_macro_calls=[1, 1],
            expected_python_fallbacks=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_config_error_when_compiling_with_preview_then_error_matches_python_once(
    test_case: NativeConfigErrorTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "orders"
    runs: list[CompileReuseRun] = []
    macro_calls: list[int] = []
    for engine in _ENGINES:
        write_counted_error_project(
            project_dir=project_dir, files={**_PROJECT_FILES, **test_case.project_files}
        )
        runs.append(
            run_reuse_compile(project_dir=project_dir, global_args=("--compiler-engine", engine))
        )
        macro_calls.append(len((project_dir / _CALL_LOG).read_text(encoding="utf-8").splitlines()))
    for name in ("python", "preview"):
        write_counted_error_project(
            project_dir=tmp_path / name, files={**_PROJECT_FILES, **test_case.project_files}
        )
    python_run: CompileReuseRun = python_engine_compile(
        project_dir=tmp_path / "python", monkeypatch=monkeypatch, capsys=capsys
    )
    preview_run, fallbacks = fallback_free_preview_compile(
        project_dir=tmp_path / "preview",
        fallbacks=_FALLBACKS,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert (
        tuple(run.returncode for run in runs),
        report_without_engine(runs[1]) == report_without_engine(runs[0]),
        stderr_without_durations(stderr=runs[1].stderr)
        == stderr_without_durations(stderr=runs[0].stderr),
        test_case.expected_report_text in runs[0].report + runs[0].stderr,
        macro_calls,
        preview_run.returncode,
        report_without_engine(preview_run).replace("preview", "python"),
        fallbacks,
    ) == (
        (1, 1),
        True,
        True,
        True,
        test_case.expected_macro_calls,
        python_run.returncode,
        report_without_engine(python_run).replace("preview", "python"),
        test_case.expected_python_fallbacks,
    ), (runs[0].report, runs[1].report, runs[1].stderr)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroExpandedValidatorErrorTestCase(
            description="unknown_model_reference_from_a_macro",
            project_files={
                "macros/upstream.py": _UPSTREAM_MACRO,
                "models/marts/customer_totals.sql": (
                    'MODEL (\n  description "Order totals per customer",\n);\n\n'
                    "SELECT * FROM @upstream()\n"
                ),
                _CALL_LOG: "",
            },
            engines=("python", "native-preview", "native"),
            expected_report_text="references unknown model 'ghost'",
            expected_macro_calls=[1, 2, 1],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_validator_error_from_macro_sql_when_compiling_then_preview_bridge_reruns_it(
    test_case: MacroExpandedValidatorErrorTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "orders"
    runs: list[CompileReuseRun] = []
    macro_calls: list[int] = []
    for engine in test_case.engines:
        write_counted_error_project(project_dir=project_dir, files=test_case.project_files)
        runs.append(
            run_reuse_compile(project_dir=project_dir, global_args=("--compiler-engine", engine))
        )
        macro_calls.append(len((project_dir / _CALL_LOG).read_text(encoding="utf-8").splitlines()))

    assert (
        [run.returncode for run in runs],
        [test_case.expected_report_text in run.report + run.stderr for run in runs],
        {report_without_engine(run) for run in runs} == {report_without_engine(runs[0])},
        macro_calls,
    ) == (
        [1] * len(test_case.engines),
        [True] * len(test_case.engines),
        True,
        test_case.expected_macro_calls,
    ), [run.report + run.stderr for run in runs]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
