from pathlib import Path

import pytest

from scripts.native_module_paths._helpers.crates import (
    native_module_path_errors,
    scan_native_crates,
)
from scripts.native_module_paths.models import NativeModulePathScan
from tests.unit.scripts.native_module_paths._helpers._test_types import (
    NativeSourceModulePathTestCase,
    RepositoryModulePathTestCase,
)
from tests.unit.scripts.native_module_paths._helpers.helpers import native_source_errors

EXCEPTIONS_MODULE: str = "sqlbuild.cli.commands.exceptions"


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSourceModulePathTestCase(
            description="module constant and helper attribute resolve",
            source=(
                f'const ERRORS_MODULE: &str = "{EXCEPTIONS_MODULE}";\n'
                'let error = imported(py, ERRORS_MODULE, "CliUserError")?;\n'
            ),
            expected_errors=(),
        ),
        NativeSourceModulePathTestCase(
            description="literal names a module attribute",
            source=f'let error = py.import("sqlbuild")?;\nlet name = "{EXCEPTIONS_MODULE}.CliUserError";\n',
            expected_errors=(),
        ),
        NativeSourceModulePathTestCase(
            description="logger constant is not imported",
            source='const LOGGER_NAME: &str = "sqlbuild.compile";\n',
            expected_errors=(),
        ),
        NativeSourceModulePathTestCase(
            description="relation names are formatted from lower-case values",
            source=(
                'let relation = format!("{schema}.{table}");\n'
                'let qualified = format!("{}.{}", text_of(schema)?, text_of(&alias)?);\n'
                'let temporary = format!(".{CACHE_FILE_NAME}.{}.tmp", id);\n'
            ),
            expected_errors=(),
        ),
        NativeSourceModulePathTestCase(
            description="unknown module literal",
            source='const MISSING_MODULE: &str = "sqlbuild.cli.no_such_module";\n',
            expected_errors=(
                "lib.rs:1: 'sqlbuild.cli.no_such_module' is not an importable module or attribute.",
            ),
        ),
        NativeSourceModulePathTestCase(
            description="helper attribute missing from a module constant",
            source=(
                f'const ERRORS_MODULE: &str =\n    "{EXCEPTIONS_MODULE}";\n'
                'let error = imported(\n    py,\n    ERRORS_MODULE,\n    "NoSuchError",\n)?;\n'
            ),
            expected_errors=(f"lib.rs:3: '{EXCEPTIONS_MODULE}' has no attribute 'NoSuchError'.",),
        ),
        NativeSourceModulePathTestCase(
            description="getattr missing from an imported literal",
            source=f'let error = py\n    .import("{EXCEPTIONS_MODULE}")?\n    .getattr("NoSuchError")?;\n',
            expected_errors=(f"lib.rs:2: '{EXCEPTIONS_MODULE}' has no attribute 'NoSuchError'.",),
        ),
        NativeSourceModulePathTestCase(
            description="literal module and attribute pair missing the attribute",
            source=f'const CALLS: [(&str, &str); 1] = [("{EXCEPTIONS_MODULE}", "NoSuchError")];\n',
            expected_errors=(f"lib.rs:1: '{EXCEPTIONS_MODULE}' has no attribute 'NoSuchError'.",),
        ),
        NativeSourceModulePathTestCase(
            description="package constant joined with a module name at runtime",
            source='let module = format!("{RUNTIME_PACKAGE}.{module}");\n',
            expected_errors=(
                "lib.rs:1: module path is built at runtime; use a complete literal module path.",
            ),
        ),
        NativeSourceModulePathTestCase(
            description="module constant passed positionally to a joined template",
            source='let module = format!(\n    "{}.{}",\n    EFFECTIVE_MODULE,\n    module,\n);\n',
            expected_errors=(
                "lib.rs:1: module path is built at runtime; use a complete literal module path.",
            ),
        ),
        NativeSourceModulePathTestCase(
            description="package prefix completed at runtime",
            source='let module = format!("sqlbuild.compiler.{module}");\n',
            expected_errors=(
                "lib.rs:1: 'sqlbuild.compiler.{module}' is not a complete dotted module path.",
                "lib.rs:1: module path is built at runtime; use a complete literal module path.",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_source_when_checking_module_paths_then_reports_errors(
    test_case: NativeSourceModulePathTestCase,
) -> None:
    assert native_source_errors(test_case.source) == test_case.expected_errors


@pytest.mark.parametrize(
    "test_case",
    [
        RepositoryModulePathTestCase(
            description="native crates import only existing Python modules and attributes",
            expected_errors=(),
            expected_logger_names=(
                "sqlbuild.cli",
                "sqlbuild.cli.commands._helpers.cost.collection",
                "sqlbuild.cli.commands.classes.prepared_compile_artifacts",
                "sqlbuild.cli.observability",
                "sqlbuild.compile",
                "sqlbuild.cost",
                "sqlbuild.executor.runtime",
                "sqlbuild.fingerprints",
                "sqlbuild.lineage",
                "sqlbuild.migrations",
                "sqlbuild.planner",
                "sqlbuild.planner.changes",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_native_crates_when_checking_then_module_paths_resolve(
    test_case: RepositoryModulePathTestCase,
) -> None:
    repository: Path = Path(__file__).resolve().parents[5]

    scan: NativeModulePathScan = scan_native_crates(root=repository)

    assert scan.references
    assert scan.logger_names == test_case.expected_logger_names
    assert native_module_path_errors(scan=scan) == test_case.expected_errors


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
