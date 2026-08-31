"""Tests for bounded scoped declaration filesystem discovery."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pytest

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_audit_files,
    discover_hook_functions,
    discover_macro_files,
    discover_model_files,
    discover_python_function_files,
    discover_scenario_files,
    discover_source_files,
    discover_sql_function_files,
    discover_sql_hook_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import (
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredMacroFile,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    DiscoverGlobalDeclarationTestCase,
    DiscoverScopedDeclarationTestCase,
    DiscoveryPathInventoryTestCase,
    InvalidScopedDeclarationRootTestCase,
    OrdinaryDiscoveryExclusionTestCase,
    StrictScopedDiscoveryTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers.helpers import (
    declaration_contents,
    discover_declarations,
)


class _DiscoveredFile(Protocol):
    relative_path: Path


@pytest.mark.parametrize(
    "test_case",
    (
        DiscoverScopedDeclarationTestCase("models", "models", "models"),
        DiscoverScopedDeclarationTestCase("unit_tests", "tests/unit", "tests/unit"),
        DiscoverScopedDeclarationTestCase("scenarios", "tests/scenarios", "tests/scenarios"),
        DiscoverScopedDeclarationTestCase("sql_hooks", "hooks/sql", "hooks/sql"),
        DiscoverScopedDeclarationTestCase("sql_functions", "functions/sql", "functions/sql"),
        DiscoverScopedDeclarationTestCase("audits", "audits", "audits"),
        DiscoverScopedDeclarationTestCase("sources", "sources", "sources"),
    ),
    ids=lambda case: case.description,
)
def test_given_declaration_below_authored_root_when_discovering_then_records_bounded_scope_facts(
    test_case: DiscoverScopedDeclarationTestCase,
    tmp_path: Path,
) -> None:
    for declaration_kind in ("macro", "enum", "constant"):
        for scope_kind in ("inherited", "local"):
            suffix, contents = declaration_contents(kind=declaration_kind)
            directory_name: str = {
                "inherited": f"{declaration_kind}s",
                "local": f"_{declaration_kind}s",
            }[scope_kind]
            relative_root: Path = Path(test_case.authored_root) / "domain" / directory_name
            file_path: Path = tmp_path / relative_root / "organization" / f"z_value{suffix}"
            file_path.parent.mkdir(parents=True)
            file_path.write_text(contents, encoding="utf-8")

            result: tuple[
                DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile, ...
            ] = discover_declarations(project_dir=tmp_path, kind=declaration_kind)

            assert len(result) == 1
            discovered: DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile = result[
                0
            ]
            assert discovered.relative_path == (relative_root / "organization" / f"z_value{suffix}")
            assert discovered.scope_kind.value == scope_kind
            assert discovered.ownership_root == Path(test_case.expected_ownership_root)
            assert discovered.owning_path == Path(test_case.authored_root) / "domain"
            assert discovered.declaration_root == relative_root
            file_path.unlink()


@pytest.mark.parametrize(
    "test_case",
    (
        DiscoverGlobalDeclarationTestCase("macro", "macro", "macros", "global"),
        DiscoverGlobalDeclarationTestCase("enum", "enum", "enums", "global"),
        DiscoverGlobalDeclarationTestCase("constant", "constant", "constants", "global"),
    ),
    ids=lambda case: case.description,
)
def test_given_top_level_public_declarations_when_discovering_then_scope_remains_global(
    test_case: DiscoverGlobalDeclarationTestCase,
    tmp_path: Path,
) -> None:
    suffix, contents = declaration_contents(kind=test_case.declaration_kind)
    file_path: Path = tmp_path / test_case.directory_name / "organization" / f"value{suffix}"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(contents, encoding="utf-8")

    discovered: DiscoveredMacroFile | DiscoveredEnumFile | DiscoveredConstantFile = (
        discover_declarations(project_dir=tmp_path, kind=test_case.declaration_kind)[0]
    )

    assert discovered.scope_kind.value == test_case.expected_scope_kind
    assert discovered.ownership_root == Path(test_case.directory_name)
    assert discovered.owning_path is None
    assert discovered.declaration_root == Path(test_case.directory_name)


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidScopedDeclarationRootTestCase(
            "top_level_inherited", "_macros/value.py", "must be below a canonical authored root"
        ),
        InvalidScopedDeclarationRootTestCase(
            "removed_local_name",
            "_local_constants/value.sql",
            "has been replaced by _constants/",
        ),
        InvalidScopedDeclarationRootTestCase(
            "nested_scoped_roots",
            "models/macros/organization/_constants/value.sql",
            "nested inside another declaration tree",
        ),
        InvalidScopedDeclarationRootTestCase(
            "scoped_root_below_global_tree",
            "macros/organization/_macros/value.py",
            "nested inside another declaration tree",
        ),
        InvalidScopedDeclarationRootTestCase(
            "global_root_below_global_tree",
            "macros/organization/constants/value.sql",
            "nested inside another declaration tree",
        ),
        InvalidScopedDeclarationRootTestCase(
            "global_root_below_scoped_tree",
            "models/macros/organization/enums/value.sql",
            "nested inside another declaration tree",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_declaration_root_when_discovering_then_raises(
    test_case: InvalidScopedDeclarationRootTestCase,
    tmp_path: Path,
) -> None:
    file_path: Path = tmp_path / test_case.relative_path
    file_path.parent.mkdir(parents=True)
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(DeclarationParseError, match=test_case.expected_error_fragment):
        discover_macro_files(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    (
        StrictScopedDiscoveryTestCase(
            "top_level_enum",
            "_enums/value.sql",
            "ENUM (name value, members [ONE]);\n",
            "must be below a canonical authored root",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_scoped_root_when_discovering_project_inputs_then_strict_discovery_raises(
    test_case: StrictScopedDiscoveryTestCase,
    tmp_path: Path,
) -> None:
    config_path: Path = tmp_path / "sqlbuild_project.toml"
    config_path.write_text('name = "demo"\nadapter = "duckdb"\n', encoding="utf-8")
    file_path: Path = tmp_path / test_case.relative_path
    file_path.parent.mkdir()
    file_path.write_text(test_case.contents, encoding="utf-8")

    with pytest.raises(DeclarationParseError, match=test_case.expected_error_fragment):
        discover_project_inputs(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    (
        OrdinaryDiscoveryExclusionTestCase(
            "model",
            "models/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "model",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "unit_test",
            "tests/unit/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "test",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "scenario",
            "tests/scenarios/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "scenario",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "hook",
            "hooks/sql/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "hook",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "function",
            "functions/sql/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "function",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "audit",
            "audits/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "audit",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "source",
            "sources/domain/_constants/value.sql",
            "CONSTANT (name scoped_value, value 1);\n",
            "source",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "python_function",
            "functions/sql/domain/_macros/value.py",
            "raise RuntimeError('must not import')\n",
            "python_function",
            (),
        ),
        OrdinaryDiscoveryExclusionTestCase(
            "python_hook",
            "hooks/sql/domain/_macros/value.py",
            "raise RuntimeError('must not import')\n",
            "python_hook",
            (),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scoped_declaration_file_when_discovering_resources_then_excludes_it(
    test_case: OrdinaryDiscoveryExclusionTestCase,
    tmp_path: Path,
) -> None:
    file_path: Path = tmp_path / test_case.relative_path
    file_path.parent.mkdir(parents=True)
    file_path.write_text(test_case.contents, encoding="utf-8")
    discoverers: dict[str, Callable[..., tuple[_DiscoveredFile, ...]]] = {
        "model": discover_model_files,
        "test": discover_test_files,
        "scenario": discover_scenario_files,
        "hook": discover_sql_hook_files,
        "function": discover_sql_function_files,
        "audit": discover_audit_files,
        "source": discover_source_files,
        "python_function": discover_python_function_files,
        "python_hook": discover_hook_functions,
    }

    result: tuple[_DiscoveredFile, ...] = discoverers[test_case.discoverer_name](
        project_dir=tmp_path
    )

    assert tuple(item.relative_path.as_posix() for item in result) == (
        test_case.expected_relative_paths
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DiscoveryPathInventoryTestCase(
            "similarly_prefixed_directory",
            ("models/_constants_archive/orders.sql",),
            ("models/_constants_archive/orders.sql",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_similarly_prefixed_directory_when_discovering_then_treats_it_as_ordinary_resource(
    test_case: DiscoveryPathInventoryTestCase,
    tmp_path: Path,
) -> None:
    file_path: Path = tmp_path / test_case.files[0]
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODEL ();\nSELECT 1\n", encoding="utf-8")

    result: tuple[_DiscoveredFile, ...] = discover_model_files(project_dir=tmp_path)

    assert tuple(file.relative_path.as_posix() for file in result) == (
        test_case.expected_relative_paths
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DiscoveryPathInventoryTestCase(
            "unsorted_scoped_macros",
            (
                "models/z/_macros/z.py",
                "models/a/_macros/z.py",
                "models/a/_macros/a.py",
                "models/a/_macros/__init__.py",
            ),
            (
                "models/a/_macros/a.py",
                "models/a/_macros/z.py",
                "models/z/_macros/z.py",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsorted_scoped_files_and_initializer_when_discovering_then_sorts_and_skips_initializer(
    test_case: DiscoveryPathInventoryTestCase,
    tmp_path: Path,
) -> None:
    for relative_path in test_case.files:
        file_path: Path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("def value():\n    return 1\n", encoding="utf-8")

    result: tuple[DiscoveredMacroFile, ...] = discover_macro_files(project_dir=tmp_path)

    assert tuple(file.relative_path.as_posix() for file in result) == (
        test_case.expected_relative_paths
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
