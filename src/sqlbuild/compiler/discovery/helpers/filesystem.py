"""Filesystem-backed discovery helpers for project inputs."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from sqlbuild.assets import get_asset_definition
from sqlbuild.checks import get_check_definition
from sqlbuild.compiler.discovery.exceptions import (
    LoaderDiscoveryError,
    PythonNodeDiscoveryError,
    SchemaParseError,
)
from sqlbuild.compiler.discovery.helpers.python_functions import parse_python_function
from sqlbuild.compiler.discovery.helpers.sql_audits import parse_sql_audit_file
from sqlbuild.compiler.discovery.helpers.sql_functions import parse_function_sql
from sqlbuild.compiler.discovery.helpers.sql_models import (
    model_header_column_locations,
    model_output_column_locations,
    parse_model_sql,
)
from sqlbuild.compiler.discovery.helpers.sql_scenarios import parse_sql_scenario_file
from sqlbuild.compiler.discovery.helpers.sql_tests import parse_sql_test_file
from sqlbuild.compiler.discovery.helpers.yml_schema import parse_schema_yml
from sqlbuild.compiler.discovery.helpers.yml_sources import parse_sources_yml
from sqlbuild.compiler.discovery.models import (
    DiscoveredAdapterFile,
    DiscoveredAssetFunction,
    DiscoveredAuditFile,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredMaterializationFile,
    DiscoveredPythonFunctionFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestFile,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.shared.constants import (
    SCHEMA_FILE_NAME,
    SEED_FILE_SUFFIX,
    YAML_FILE_SUFFIXES,
)
from sqlbuild.loaders import LoaderDefinition, get_loader_definition
from sqlbuild.shared.models import AssetDefinition, CheckDefinition, TaskDefinition
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.tasks import get_task_definition


def discover_model_files(
    *, project_dir: Path, sqlglot_enabled: bool = True
) -> tuple[DiscoveredSqlModelFile, ...]:
    """Discover SQL model files under models/."""

    model_root: Path = project_dir / "models"
    if not model_root.is_dir():
        return ()

    discovered_model_files: list[DiscoveredSqlModelFile] = []
    file_path: Path
    for file_path in sorted(model_root.rglob("*.sql")):
        contents: str = file_path.read_text(encoding="utf-8")
        header_values: dict[str, object]
        query_sql: str
        header_values, query_sql = parse_model_sql(contents, file_path)
        discovered_model_files.append(
            DiscoveredSqlModelFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                header_values=header_values,
                header_column_locations=model_header_column_locations(
                    contents=contents,
                    relative_path=file_path.relative_to(project_dir),
                ),
                output_column_locations=model_output_column_locations(
                    contents=contents,
                    relative_path=file_path.relative_to(project_dir),
                    sqlglot_enabled=sqlglot_enabled,
                ),
                query_sql=query_sql,
            )
        )
    return tuple(discovered_model_files)


def discover_sql_function_files(*, project_dir: Path) -> tuple[DiscoveredSqlFunctionFile, ...]:
    """Discover SQL function files under functions/sql/."""

    function_root: Path = project_dir / "functions" / "sql"
    if not function_root.is_dir():
        return ()

    discovered_function_files: list[DiscoveredSqlFunctionFile] = []
    file_path: Path
    for file_path in sorted(function_root.rglob("*.sql")):
        contents: str = file_path.read_text(encoding="utf-8")
        header_values: dict[str, object]
        body_sql: str
        header_values, body_sql = parse_function_sql(contents, file_path)
        discovered_function_files.append(
            DiscoveredSqlFunctionFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                header_values=header_values,
                body_sql=body_sql,
            )
        )
    return tuple(discovered_function_files)


def discover_python_function_files(
    *, project_dir: Path
) -> tuple[DiscoveredPythonFunctionFile, ...]:
    """Discover Python function files under functions/python/."""

    function_root: Path = project_dir / "functions" / "python"
    if not function_root.is_dir():
        return ()

    discovered_function_files: list[DiscoveredPythonFunctionFile] = []
    file_path: Path
    for file_path in sorted(function_root.rglob("*.py")):
        contents: str = file_path.read_text(encoding="utf-8")
        header_values: dict[str, object]
        entry_point: str
        body_python: str
        header_values, entry_point, body_python = parse_python_function(contents, file_path)
        discovered_function_files.append(
            DiscoveredPythonFunctionFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                header_values=header_values,
                entry_point=entry_point,
                body_python=body_python,
            )
        )
    return tuple(discovered_function_files)


def discover_schema_files(*, project_dir: Path) -> tuple[DiscoveredSchemaFile, ...]:
    """Discover model schema.yml files and seed declaration .yml files."""

    schema_paths: list[Path] = []
    models_root: Path = project_dir / "models"
    seeds_root: Path = project_dir / "seeds"

    if models_root.is_dir():
        schema_paths.extend(sorted(models_root.rglob(SCHEMA_FILE_NAME)))
    if seeds_root.is_dir():
        yaml_path: Path
        for yaml_path in sorted(seeds_root.rglob("*.yaml")):
            raise SchemaParseError(
                f"Seed declaration file {yaml_path.relative_to(project_dir)} must use .yml; "
                ".yaml is not supported"
            )
        schema_paths.extend(sorted(seeds_root.rglob("*.yml")))

    deduped_paths: tuple[Path, ...] = tuple(dict.fromkeys(schema_paths))
    discovered_schema_files: list[DiscoveredSchemaFile] = []
    file_path: Path
    for file_path in deduped_paths:
        contents: str = file_path.read_text(encoding="utf-8")
        model_entries: tuple[SchemaModelEntry, ...]
        seed_entries: tuple[SchemaSeedEntry, ...]
        model_entries, seed_entries = parse_schema_yml(contents, file_path)
        discovered_schema_files.append(
            DiscoveredSchemaFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                model_entries=model_entries,
                seed_entries=seed_entries,
            )
        )
    return tuple(discovered_schema_files)


def discover_source_files(*, project_dir: Path) -> tuple[DiscoveredSourceFile, ...]:
    """Discover source declaration YAML files under sources/."""

    sources_root: Path = project_dir / "sources"
    if not sources_root.is_dir():
        return ()

    yaml_paths: tuple[Path, ...] = tuple(
        sorted(path for path in sources_root.iterdir() if path.suffix in YAML_FILE_SUFFIXES)
    )
    discovered_source_files: list[DiscoveredSourceFile] = []
    file_path: Path
    for file_path in yaml_paths:
        contents: str = file_path.read_text(encoding="utf-8")
        source_entries: tuple[SourceEntry, ...] = parse_sources_yml(contents, file_path)
        discovered_source_files.append(
            DiscoveredSourceFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                source_entries=source_entries,
            )
        )
    return tuple(discovered_source_files)


def discover_seed_files(*, project_dir: Path) -> tuple[DiscoveredSeedFile, ...]:
    """Discover seed CSV files under seeds/."""

    seeds_root: Path = project_dir / "seeds"
    if not seeds_root.is_dir():
        return ()

    return tuple(
        DiscoveredSeedFile(
            file_path=file_path,
            relative_path=file_path.relative_to(project_dir),
        )
        for file_path in sorted(seeds_root.rglob("*"))
        if file_path.is_file() and file_path.suffix == SEED_FILE_SUFFIX
    )


def discover_test_files(*, project_dir: Path) -> tuple[DiscoveredSqlTestFile, ...]:
    """Discover SQL-native unit test files under tests/unit/."""

    tests_root: Path = project_dir / "tests" / "unit"
    if not tests_root.is_dir():
        return ()

    discovered_test_files: list[DiscoveredSqlTestFile] = []
    file_path: Path
    for file_path in sorted(tests_root.rglob("*.sql")):
        contents: str = file_path.read_text(encoding="utf-8")
        discovered_test_files.append(
            DiscoveredSqlTestFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                blocks=parse_sql_test_file(contents, file_path),
            )
        )
    return tuple(discovered_test_files)


def discover_scenario_files(*, project_dir: Path) -> tuple[DiscoveredSqlScenarioFile, ...]:
    """Discover SQL-native scenario files under tests/scenarios/."""

    scenarios_root: Path = project_dir / "tests" / "scenarios"
    if not scenarios_root.is_dir():
        return ()

    discovered_scenario_files: list[DiscoveredSqlScenarioFile] = []
    file_path: Path
    for file_path in sorted(scenarios_root.rglob("*.sql")):
        contents: str = file_path.read_text(encoding="utf-8")
        discovered_scenario_files.append(
            parse_sql_scenario_file(
                contents=contents,
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
            )
        )
    return tuple(discovered_scenario_files)


def discover_audit_files(*, project_dir: Path) -> tuple[DiscoveredAuditFile, ...]:
    """Discover audit SQL files under audits/."""

    audits_root: Path = project_dir / "audits"
    if not audits_root.is_dir():
        return ()

    discovered_audit_files: list[DiscoveredAuditFile] = []
    file_path: Path
    for file_path in sorted(audits_root.rglob("*.sql")):
        contents: str = file_path.read_text(encoding="utf-8")
        discovered_audit_files.append(
            DiscoveredAuditFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                blocks=parse_sql_audit_file(contents, file_path),
            )
        )
    return tuple(discovered_audit_files)


def discover_macro_files(*, project_dir: Path) -> tuple[DiscoveredMacroFile, ...]:
    """Discover project macro Python files under macros/."""

    macros_root: Path = project_dir / "macros"
    if not macros_root.is_dir():
        return ()

    return tuple(
        DiscoveredMacroFile(
            file_path=file_path,
            relative_path=file_path.relative_to(project_dir),
            contents=file_path.read_text(encoding="utf-8"),
        )
        for file_path in sorted(macros_root.rglob("*.py"))
    )


def discover_materialization_files(
    *, project_dir: Path
) -> tuple[DiscoveredMaterializationFile, ...]:
    """Discover custom materialization Python files under materializations/."""

    materializations_root: Path = project_dir / "materializations"
    if not materializations_root.is_dir():
        return ()

    return tuple(
        DiscoveredMaterializationFile(
            file_path=file_path,
            relative_path=file_path.relative_to(project_dir),
            name=file_path.stem,
        )
        for file_path in sorted(materializations_root.rglob("*.py"))
        if file_path.stem != "__init__"
    )


def discover_loader_functions(*, project_dir: Path) -> tuple[DiscoveredLoaderFunction, ...]:
    """Discover decorated source loader functions under loaders/."""

    loaders_root: Path = project_dir / "loaders"
    if not loaders_root.is_dir():
        return ()

    discovered: list[DiscoveredLoaderFunction] = []
    file_path: Path
    for file_path in sorted(loaders_root.rglob("*.py")):
        if file_path.stem == "__init__":
            continue
        module: ModuleType = _load_loader_module(file_path=file_path, project_dir=project_dir)
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            definition: LoaderDefinition | None = get_loader_definition(value)
            if definition is None:
                continue
            discovered.append(
                DiscoveredLoaderFunction(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=definition.name,
                    function=value,
                    depends_on=definition.depends_on,
                    target=definition.target,
                    write_strategy=definition.write_strategy,
                    cursor_column=definition.cursor_column,
                    unique_key=definition.unique_key,
                    columns=definition.columns,
                    contract=definition.contract,
                )
            )
    return tuple(discovered)


def discover_task_functions(*, project_dir: Path) -> tuple[DiscoveredTaskFunction, ...]:
    """Discover decorated task functions under tasks/."""

    tasks_root: Path = project_dir / "tasks"
    if not tasks_root.is_dir():
        return ()

    discovered: list[DiscoveredTaskFunction] = []
    file_path: Path
    for file_path in sorted(tasks_root.rglob("*.py")):
        if file_path.stem == "__init__":
            continue
        module: ModuleType = _load_python_node_module(
            file_path=file_path,
            project_dir=project_dir,
            node_folder="tasks",
        )
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            definition: TaskDefinition | None = get_task_definition(value)
            if definition is None:
                continue
            discovered.append(
                DiscoveredTaskFunction(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=definition.name,
                    function=value,
                    depends_on=definition.depends_on,
                    tags=definition.tags,
                    group=definition.group,
                    description=definition.description,
                    meta=definition.meta,
                    retry=definition.retry,
                )
            )
    return tuple(discovered)


def discover_asset_functions(*, project_dir: Path) -> tuple[DiscoveredAssetFunction, ...]:
    """Discover decorated asset functions under assets/."""

    assets_root: Path = project_dir / "assets"
    if not assets_root.is_dir():
        return ()

    discovered: list[DiscoveredAssetFunction] = []
    file_path: Path
    for file_path in sorted(assets_root.rglob("*.py")):
        if file_path.stem == "__init__":
            continue
        module: ModuleType = _load_python_node_module(
            file_path=file_path,
            project_dir=project_dir,
            node_folder="assets",
        )
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            definition: AssetDefinition | None = get_asset_definition(value)
            if definition is None:
                continue
            discovered.append(
                DiscoveredAssetFunction(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=definition.name,
                    function=value,
                    depends_on=definition.depends_on,
                    tags=definition.tags,
                    group=definition.group,
                    description=definition.description,
                    meta=definition.meta,
                    columns=definition.columns,
                    column_lineage=definition.column_lineage,
                    retry=definition.retry,
                )
            )
    return tuple(discovered)


def discover_check_functions(*, project_dir: Path) -> tuple[DiscoveredCheckFunction, ...]:
    """Discover decorated check functions under checks/."""

    checks_root: Path = project_dir / "checks"
    if not checks_root.is_dir():
        return ()

    discovered: list[DiscoveredCheckFunction] = []
    file_path: Path
    for file_path in sorted(checks_root.rglob("*.py")):
        if file_path.stem == "__init__":
            continue
        module: ModuleType = _load_python_node_module(
            file_path=file_path,
            project_dir=project_dir,
            node_folder="checks",
        )
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            definition: CheckDefinition | None = get_check_definition(value)
            if definition is None:
                continue
            discovered.append(
                DiscoveredCheckFunction(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=definition.name,
                    function=value,
                    depends_on=definition.depends_on,
                    severity=definition.severity,
                    tags=definition.tags,
                    group=definition.group,
                    description=definition.description,
                    meta=definition.meta,
                )
            )
    return tuple(discovered)


def _load_loader_module(*, file_path: Path, project_dir: Path) -> ModuleType:
    module_name: str = "sqlbuild_project_loader_" + "_".join(
        file_path.relative_to(project_dir).with_suffix("").parts
    )
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise LoaderDiscoveryError(f"Could not load source loader file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise LoaderDiscoveryError(
            f"Failed to import source loader file {file_path.relative_to(project_dir)}: {error}"
        ) from error
    finally:
        sys.path = old_path
    return module


def _load_python_node_module(*, file_path: Path, project_dir: Path, node_folder: str) -> ModuleType:
    module_name: str = "sqlbuild_project_python_node_" + "_".join(
        file_path.relative_to(project_dir).with_suffix("").parts
    )
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise PythonNodeDiscoveryError(f"Could not load Python node file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise PythonNodeDiscoveryError(
            f"Failed to import Python node file {file_path.relative_to(project_dir)}: {error}"
        ) from error
    finally:
        sys.path = old_path
    return module


def discover_adapter_file(*, project_dir: Path) -> DiscoveredAdapterFile | None:
    """Detect a project-level adapter.py without importing it."""

    file_path: Path = project_dir / "adapter.py"
    if not file_path.is_file():
        return None

    return DiscoveredAdapterFile(
        file_path=file_path,
        relative_path=file_path.relative_to(project_dir),
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
