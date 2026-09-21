from collections.abc import Callable
from pathlib import Path
from typing import cast

from sqlbuild import _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_constant_files,
    discover_enum_files,
    discover_macro_files,
)
from sqlbuild.compiler.discovery._helpers.sql import model_files as model_file_helpers
from sqlbuild.compiler.discovery.models import (
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredMacroFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestCase,
    SqlTestParameterDeclaration,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    LoadProjectConfigTestCase,
)

_DECLARATION_CONTENTS_BY_KIND: dict[str, tuple[str, str]] = {
    "macro": (".py", "def scoped_value():\n    return 1\n"),
    "enum": (".sql", "ENUM (name scoped_value, members [ONE, TWO]);\n"),
    "constant": (".sql", "CONSTANT (name scoped_value, value 1);\n"),
}
_DECLARATION_DISCOVERER_BY_KIND: dict[
    str,
    Callable[
        ...,
        tuple[DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile, ...],
    ],
] = {
    "macro": discover_macro_files,
    "enum": discover_enum_files,
    "constant": discover_constant_files,
}


def _standard_model_header(index: int, suffix: str) -> str:
    return (
        f"name model_{suffix}, enabled true, columns (col_{suffix} "
        '(type DECIMAL(10,2), nullable false, description "Order total"))'
    )


def _constant_model_header(_index: int, suffix: str) -> str:
    return (
        f"constants (_set_{suffix} {{FR, GB, FR}}, "
        f"_array_{suffix} constant(value [1, 2], render_as array))"
    )


def _hook_model_header(index: int, suffix: str) -> str:
    return (
        f'pre_hooks [inline_sql("select {index}"), sql("record_{suffix}", '
        'table: "orders"), python("notify", attempts: 2, urgent: true)]'
    )


def _audit_model_header(_index: int, suffix: str) -> str:
    return (
        f"audits [rate_{suffix} (thresholds (warn (outside -1.5 2.5)))], "
        f'parent __ref("orders_{suffix}")'
    )


def _template_model_header(_index: int, suffix: str) -> str:
    return f"schema dev_${{user_{suffix}}}, tags [core, 'daily orders'], value null"


def _unicode_column_model_header(_index: int, suffix: str) -> str:
    return (
        f"columns (café_{suffix} (type TIMESTAMP_NTZ(9), audits "
        "[accepted_values (values [placed, completed])]))"
    )


def _numeric_model_header(index: int, suffix: str) -> str:
    numeric_headers: tuple[str, ...] = (
        f"unicode_integer_{suffix} +١٢٣",
        f"unicode_integer_{suffix} -१२३",
        f"unicode_float_{suffix} ١٢.٥",
        f"unicode_float_{suffix} -१२.५",
        f"numeric_character_{suffix} ²",
        f"large_{suffix} {10**40 + index}, ratio_{suffix} +.25",
    )
    return numeric_headers[(index // 10) % len(numeric_headers)]


def _escaped_model_header(_index: int, suffix: str) -> str:
    return f'description "escaped \\"value_{suffix}\\"", config (x [a, b])'


def _duplicate_or_control_model_header(index: int, suffix: str) -> str:
    headers: tuple[str, str] = (
        'post_hooks [python("\u001c")]',
        f"duplicate_{suffix} one, duplicate_{suffix} two",
    )
    return headers[index % 20 == 8]


def _invalid_model_header(_index: int, suffix: str) -> str:
    return f"columns (col_{suffix} (type DECIMAL(10,2))"


_MODEL_HEADER_BUILDERS: tuple[Callable[[int, str], str], ...] = (
    _standard_model_header,
    _constant_model_header,
    _hook_model_header,
    _audit_model_header,
    _template_model_header,
    _unicode_column_model_header,
    _numeric_model_header,
    _escaped_model_header,
    _duplicate_or_control_model_header,
    _invalid_model_header,
)


def _validate_successful_native_header(
    *,
    native_values: dict[str, object] | None,
    native_offsets: list[tuple[str, int, int]] | None,
    parent_values: dict[str, object] | None,
) -> None:
    assert native_values is not None
    assert model_file_helpers._project_native_header_map(native_values) == parent_values
    assert native_offsets is not None


def _validate_failed_native_header(
    *,
    native_values: dict[str, object] | None,
    native_offsets: list[tuple[str, int, int]] | None,
    parent_values: dict[str, object] | None,
) -> None:
    assert native_values is None
    assert parent_values is None
    assert native_offsets is None


_NATIVE_HEADER_VALIDATORS: tuple[Callable[..., None], ...] = (
    _validate_successful_native_header,
    _validate_failed_native_header,
)


def assert_generated_model_header_corpus_parity() -> bool:
    """Assert native MODEL-header parsing matches the Python reference corpus."""

    headers: list[str] = [
        "config (columns (nested (type INTEGER))), columns (top (type INTEGER))",
        "config (columns (nested (type INTEGER)))",
    ]
    for index in range(9_998):
        suffix: str = str(index)
        headers.append(_MODEL_HEADER_BUILDERS[index % len(_MODEL_HEADER_BUILDERS)](index, suffix))

    native_results: list[
        tuple[dict[str, object] | None, list[tuple[str, int, int]] | None, str | None]
    ] = _native.parse_model_headers(headers)
    for header, (native_values, native_offsets, native_error) in zip(
        headers, native_results, strict=True
    ):
        try:
            parent_values: dict[str, object] | None = model_file_helpers._ModelHeaderParser(
                header=header
            ).parse()
            parent_error: str | None = None
        except model_file_helpers.ModelHeaderSyntaxError as error:
            parent_values = None
            parent_error = str(error)
        assert native_error == parent_error
        _NATIVE_HEADER_VALIDATORS[native_values is None](
            native_values=native_values,
            native_offsets=native_offsets,
            parent_values=parent_values,
        )
    return True


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    return (actual, cast(T, expected))[expected is not None]


def write_project_config_test_files(
    *, tmp_path: Path, test_case: LoadProjectConfigTestCase
) -> None:
    project_file: Path = tmp_path / "sqlbuild_project.toml"
    project_file.write_text(test_case.project_file_contents, encoding="utf-8")


def declaration_contents(*, kind: str) -> tuple[str, str]:
    return _DECLARATION_CONTENTS_BY_KIND[kind]


def discover_declarations(
    *, project_dir: Path, kind: str
) -> tuple[DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile, ...]:
    return _DECLARATION_DISCOVERER_BY_KIND[kind](project_dir=project_dir)


def discovered_test_parameters(
    *, blocks: tuple[DiscoveredSqlTestBlock, ...]
) -> tuple[SqlTestParameterDeclaration, ...]:
    parameters: list[SqlTestParameterDeclaration] = []
    block: DiscoveredSqlTestBlock
    for block in blocks:
        parameters.extend(block.parameters)
    return tuple(parameters)


def discovered_test_cases(
    *, blocks: tuple[DiscoveredSqlTestBlock, ...]
) -> tuple[DiscoveredSqlTestCase, ...]:
    cases: list[DiscoveredSqlTestCase] = []
    block: DiscoveredSqlTestBlock
    for block in blocks:
        cases.extend(block.cases)
    return tuple(cases)


def discovered_test_case_values(
    *, cases: tuple[DiscoveredSqlTestCase, ...]
) -> tuple[tuple[object, ...], ...]:
    case_values: list[tuple[object, ...]] = []
    test_case: DiscoveredSqlTestCase
    for test_case in cases:
        case_values.append(tuple(value.value for _name, value in test_case.values))
    return tuple(case_values)
