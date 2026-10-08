"""Every engine reports attachment errors identically; bridge-independent ones never re-run."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.corpus.attachment_failure_cases import (
    attachment_failure_cases,
)
from scripts.compiler_differential.constants import FAILURE_BASE_MART, FAILURE_MART_PATH
from scripts.compiler_differential.models import FailureCase
from tests.e2e.src.sqlbuild.cli.commands.main.compile.attachment_errors._test_types import (
    NativeAttachmentErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    lifecycle_error_type,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
)

_ENGINES: tuple[str, ...] = ("python", "native", "native-preview")
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
_ERROR_TYPES: tuple[str, str, str] = ("CompileInputError", "CompileInputError", "CompileInputError")
_CASES: dict[str, FailureCase] = {case.name: case for case in attachment_failure_cases()}


@pytest.mark.parametrize(
    "test_case",
    [
        NativeAttachmentErrorTestCase(
            description="an unknown audit run scope",
            case_name="generic-audit-unknown-run-scope",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="an audit argument overriding the implicit model",
            case_name="generic-audit-overrides-implicit-model",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="a cursor intrinsic in a generic audit re-runs as it reads expanded SQL",
            case_name="generic-audit-cursor-intrinsic",
            expected_macro_calls=(1, 1, 2),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="an unknown project variable in audit SQL",
            case_name="audit-unknown-project-variable",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="an unknown project variable inside doubled backticks in audit SQL",
            case_name="audit-variable-in-doubled-backticks",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="a SQL function without returns",
            case_name="sql-function-missing-returns",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="an unsupported template namespace in a function header",
            case_name="sql-function-template-namespace",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
        NativeAttachmentErrorTestCase(
            description="an unknown variable in a source description",
            case_name="source-description-unknown-variable",
            expected_macro_calls=(1, 1, 1),
            expected_error_types=_ERROR_TYPES,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_attachment_error_when_compiling_with_each_engine_then_errors_and_types_match(
    test_case: NativeAttachmentErrorTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case: FailureCase = _CASES[test_case.case_name]
    runs: list[CompileReuseRun] = []
    macro_calls: list[int] = []
    error_types: list[str] = []
    project_dir: Path = tmp_path / "orders"
    files: dict[str, str] = {
        **case.files,
        "macros/counted.py": _COUNTED_MACRO,
        FAILURE_MART_PATH: FAILURE_BASE_MART.replace("SUM(amount)", "SUM(@counted('amount'))"),
        _CALL_LOG: "",
    }
    for engine in _ENGINES:
        shutil.rmtree(project_dir, ignore_errors=True)
        for relative_path, contents in files.items():
            write_project_file(project_dir, relative_path, contents)
        runs.append(
            run_reuse_compile(project_dir=project_dir, global_args=("--compiler-engine", engine))
        )
        macro_calls.append(len((project_dir / _CALL_LOG).read_text(encoding="utf-8").splitlines()))
        error_types.append(
            lifecycle_error_type(project_dir=project_dir, engine=engine, monkeypatch=monkeypatch)
        )

    assert (
        tuple(run.returncode for run in runs),
        {report_without_engine(run) for run in runs[1:]} == {report_without_engine(runs[0])},
        {stderr_without_durations(stderr=run.stderr) for run in runs[1:]}
        == {stderr_without_durations(stderr=runs[0].stderr)},
        f"[{case.expected_code}]" in runs[0].report + runs[0].stderr,
        str(case.expected_message) in runs[0].report + runs[0].stderr,
        tuple(macro_calls),
        tuple(error_types),
    ) == (
        (1, 1, 1),
        True,
        True,
        True,
        True,
        test_case.expected_macro_calls,
        test_case.expected_error_types,
    ), (
        runs[0].report,
        runs[2].report,
        runs[2].stderr,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
