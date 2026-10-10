"""Every engine reports macro errors as Python does and runs each macro call once."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.compiler_differential.constants import FAILURE_BASE_FILES, FAILURE_BASE_MART
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    MacroErrorLifecycleTestCase,
    NativeMacroErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    lifecycle_error_type,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
)

_ENGINES: tuple[str, ...] = ("native", "native-preview")
_CALL_LOG: str = "macro_calls.log"
_MACROS: str = (
    "from pathlib import Path\n\n\n"
    "def _log(name: str) -> None:\n"
    f"    with (Path(__file__).resolve().parents[1] / {_CALL_LOG!r}).open(\n"
    '        "a", encoding="utf-8"\n'
    "    ) as log:\n"
    '        _ = log.write(f"{name}\\n")\n\n\n'
    "def counted(expression: str) -> str:\n"
    '    """Return the expression, logging each execution."""\n'
    '    _log(f"counted {expression}")\n'
    "    return expression\n\n\n"
    "def explode(expression: str) -> str:\n"
    '    """Fail after logging the call."""\n'
    '    _log(f"explode {expression}")\n'
    '    raise ValueError(f"cannot render {expression}")\n\n\n'
    "def answer() -> int:\n"
    '    """Return a value that is not SQL."""\n'
    '    _log("answer")\n'
    "    return 42\n\n\n"
    "def upstream() -> str:\n"
    '    """Read a model that does not exist."""\n'
    '    _log("upstream")\n'
    "    return '__ref(\"ghost\")'\n"
)
_MART_MACROS: str = (
    "def mart_only(expression: str) -> str:\n"
    '    """Qualify an expression for marts."""\n'
    "    return expression\n"
)
_CYCLIC_MACROS: str = (
    'def ping(expression: str) -> str:\n    """Call pong."""\n    return pong(expression)\n\n\n'
    'def pong(expression: str) -> str:\n    """Call ping."""\n    return ping(expression)\n'
)
_COUNTED_MART: str = FAILURE_BASE_MART.replace("SUM(amount)", "SUM(@counted('amount'))")
_STAGING_PATH: str = "models/staging/stg_orders.sql"
_MART_PATH: str = "models/marts/customer_totals.sql"
_STAGING_PREFIX: str = (
    'MODEL (\n  description "Staged orders",\n);\n\nSELECT order_id, customer_id, '
)
_STAGING_SUFFIX: str = ' AS amount, status\nFROM __source("raw_orders")\n'


@pytest.mark.parametrize(
    "test_case",
    [
        NativeMacroErrorTestCase(
            description="macro_raises_after_a_side_effect",
            project_files={_STAGING_PATH: _STAGING_PREFIX + "@explode('amount')" + _STAGING_SUFFIX},
            expected_report_text="stg_orders.sql' failed: cannot render amount",
            expected_macro_runs=["counted amount", "explode amount"],
        ),
        NativeMacroErrorTestCase(
            description="macro_returns_a_value_that_is_not_sql",
            project_files={_STAGING_PATH: _STAGING_PREFIX + "@answer()" + _STAGING_SUFFIX},
            expected_report_text="must return a SQL string when used directly in SQL",
            expected_macro_runs=["counted amount", "answer"],
        ),
        NativeMacroErrorTestCase(
            description="macro_arguments_do_not_parse",
            project_files={
                _STAGING_PATH: _STAGING_PREFIX + "@counted('amount',,)" + _STAGING_SUFFIX
            },
            expected_report_text="could not be parsed",
            expected_macro_runs=["counted amount"],
        ),
        NativeMacroErrorTestCase(
            description="unknown_macro",
            project_files={_STAGING_PATH: _STAGING_PREFIX + "@missing('amount')" + _STAGING_SUFFIX},
            expected_report_text="Unknown macro '@missing'",
            expected_macro_runs=["counted amount"],
        ),
        NativeMacroErrorTestCase(
            description="private_macro_helper",
            project_files={_STAGING_PATH: _STAGING_PREFIX + "@_log('amount')" + _STAGING_SUFFIX},
            expected_report_text="Unknown macro '@_log'",
            expected_macro_runs=["counted amount"],
        ),
        NativeMacroErrorTestCase(
            description="macro_in_a_sibling_scope",
            project_files={
                _STAGING_PATH: _STAGING_PREFIX + "@mart_only('amount')" + _STAGING_SUFFIX,
                "models/marts/_sqlbuild/macros/local.py": _MART_MACROS,
            },
            expected_report_text="stg_orders.sql' is inaccessible",
            expected_macro_runs=["counted amount"],
        ),
        NativeMacroErrorTestCase(
            description="macro_call_cycle",
            project_files={"macros/cyclic.py": _CYCLIC_MACROS},
            expected_report_text="Macro call cycle in 'macros/cyclic.py': ping -> pong -> ping",
            expected_macro_runs=[],
        ),
        NativeMacroErrorTestCase(
            description="first_of_two_failing_models",
            project_files={
                _STAGING_PATH: _STAGING_PREFIX + "@explode('amount')" + _STAGING_SUFFIX,
                _MART_PATH: FAILURE_BASE_MART.replace("SUM(amount)", "SUM(@explode('total'))"),
            },
            expected_report_text="customer_totals.sql' failed: cannot render total",
            expected_macro_runs=["explode total"],
        ),
        NativeMacroErrorTestCase(
            description="reference_error_in_macro_sql",
            project_files={
                _STAGING_PATH: _STAGING_PREFIX
                + "amount FROM @upstream() UNION ALL SELECT 1, 2, amount"
                + _STAGING_SUFFIX
            },
            expected_report_text="references unknown model 'ghost'",
            expected_macro_runs=["counted amount", "upstream"],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_error_when_compiling_with_each_engine_then_error_matches_python_once(
    test_case: NativeMacroErrorTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "orders"
    runs: list[CompileReuseRun] = []
    macro_runs: list[list[str]] = []
    for engine in _ENGINES:
        shutil.rmtree(project_dir, ignore_errors=True)
        for relative_path, contents in {
            **FAILURE_BASE_FILES,
            "macros/orders.py": _MACROS,
            _MART_PATH: _COUNTED_MART,
            _CALL_LOG: "",
            **test_case.project_files,
        }.items():
            write_project_file(project_dir, relative_path, contents)
        runs.append(
            run_reuse_compile(project_dir=project_dir, global_args=("--compiler-engine", engine))
        )
        macro_runs.append((project_dir / _CALL_LOG).read_text(encoding="utf-8").splitlines())

    assert (
        tuple(run.returncode for run in runs),
        {report_without_engine(run) for run in runs} == {report_without_engine(runs[0])},
        {stderr_without_durations(stderr=run.stderr) for run in runs}
        == {stderr_without_durations(stderr=runs[0].stderr)},
        test_case.expected_report_text in runs[0].report + runs[0].stderr,
        macro_runs,
    ) == (
        (1,) * len(_ENGINES),
        True,
        True,
        True,
        [test_case.expected_macro_runs] * len(_ENGINES),
    ), tuple(run.report + run.stderr for run in runs)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroErrorLifecycleTestCase(
            description="macro_raises_after_a_side_effect",
            project_files={_STAGING_PATH: _STAGING_PREFIX + "@explode('amount')" + _STAGING_SUFFIX},
            expected_error_types=("CompileInputError",) * 2,
        ),
        MacroErrorLifecycleTestCase(
            description="unknown_macro",
            project_files={_STAGING_PATH: _STAGING_PREFIX + "@missing('amount')" + _STAGING_SUFFIX},
            expected_error_types=("CompileInputError",) * 2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_error_when_compiling_with_each_engine_then_lifecycle_error_type_matches(
    test_case: MacroErrorLifecycleTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error_types: list[str] = []
    for engine in _ENGINES:
        project_dir: Path = tmp_path / engine
        for relative_path, contents in {
            **FAILURE_BASE_FILES,
            "macros/orders.py": _MACROS,
            _MART_PATH: _COUNTED_MART,
            _CALL_LOG: "",
            **test_case.project_files,
        }.items():
            write_project_file(project_dir, relative_path, contents)
        error_types.append(
            lifecycle_error_type(project_dir=project_dir, engine=engine, monkeypatch=monkeypatch)
        )

    assert tuple(error_types) == test_case.expected_error_types, test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
