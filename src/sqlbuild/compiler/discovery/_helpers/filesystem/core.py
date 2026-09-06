"""Filesystem-backed discovery helpers for project inputs."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import get_type_hints

from pydantic import ValidationError

from sqlbuild.compiler.discovery._helpers.python.functions import parse_python_function
from sqlbuild.compiler.discovery._helpers.sql.audits import parse_sql_audit_file
from sqlbuild.compiler.discovery._helpers.sql.declarations import (
    parse_constant_declaration_file,
    parse_enum_declaration_file,
    parse_model_constant_declarations,
    parse_model_enum_declarations,
    parse_model_schema_declaration_file,
)
from sqlbuild.compiler.discovery._helpers.sql.functions import parse_function_sql
from sqlbuild.compiler.discovery._helpers.sql.hooks import parse_sql_hook_file
from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    model_header_column_locations,
    model_output_column_locations,
    parse_model_sql,
)
from sqlbuild.compiler.discovery._helpers.sql.scenarios import parse_sql_scenario_file
from sqlbuild.compiler.discovery._helpers.sql.tests import parse_sql_test_file
from sqlbuild.compiler.discovery._helpers.yml.schema import parse_schema_yml
from sqlbuild.compiler.discovery._helpers.yml.sources import parse_sources_yml
from sqlbuild.compiler.discovery.constants import (
    CANONICAL_AUTHORED_ROOTS,
    MODEL_SCHEMAS_DIRECTORY_NAME,
    PYTHON_FACTORY_FOLDER,
    PYTHON_INIT_MODULE_STEM,
    PYTHON_LOADER_FOLDER,
    PYTHON_NODE_KIND_VOWELS,
    SCHEMA_FILE_NAME,
    SEED_FILE_SUFFIX,
    SQL_TESTS_OWNERSHIP_ROOT,
    YAML_FILE_SUFFIXES,
)
from sqlbuild.compiler.discovery.exceptions import (
    DeclarationParseError,
    EventExporterDiscoveryError,
    LoaderDiscoveryError,
    ProviderDiscoveryError,
    PythonNodeDiscoveryError,
    SchemaParseError,
)
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAdapterFile,
    DiscoveredAssetFunction,
    DiscoveredAuditFactory,
    DiscoveredAuditFile,
    DiscoveredCheckFunction,
    DiscoveredCommandOutputSink,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredEventExporter,
    DiscoveredEventExporterDeclaration,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredMaterializationFile,
    DiscoveredModelSchemaFile,
    DiscoveredProvider,
    DiscoveredProviderUsage,
    DiscoveredPythonFunctionFile,
    DiscoveredPythonNodeFunctions,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
    DiscoveredTaskFunction,
    DiscoveryFileFault,
    EnumDeclaration,
)
from sqlbuild.compiler.resource_names.main._validate_resource_identity import (
    validate_resource_identity,
)
from sqlbuild.compiler.scopes.constants import (
    DECLARATION_DIRECTORY_FACTS,
    GLOBAL_DECLARATION_DIRECTORIES,
    INHERITED_DECLARATION_DIRECTORIES,
    LOCAL_DECLARATION_DIRECTORIES,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind
from sqlbuild.observability import LifecycleEvent
from sqlbuild.provider.exceptions import ProviderInputError
from sqlbuild.providers import Provider
from sqlbuild.python_nodes.main.read_asset_definition import read_asset_definition
from sqlbuild.python_nodes.main.read_audit_factory_definition import (
    read_audit_factory_definition,
)
from sqlbuild.python_nodes.main.read_check_definition import read_check_definition
from sqlbuild.python_nodes.main.read_factory_definition import read_factory_definition
from sqlbuild.python_nodes.main.read_hook_definition import read_hook_definition
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.main.read_task_definition import read_task_definition
from sqlbuild.python_nodes.models import (
    AssetDefinition,
    AuditCase,
    AuditFactoryDefinition,
    CheckDefinition,
    FactoryDefinition,
    HookDefinition,
    LoaderDefinition,
    TaskDefinition,
)
from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORTER_EVENT_PARAMETER_NAME
from sqlbuild.runtime.event_exporting.models import LifecycleEventSinkDefinition
from sqlbuild.sinks import (
    get_lifecycle_event_sink_definition,
)
from sqlbuild.spec.contracts.models import SchemaModelEntry, SchemaSeedEntry, SourceEntry

_PYTHON_NODE_KIND_FOLDERS: tuple[str, ...] = ("loaders", "tasks", "assets", "checks")
_PYTHON_NODE_FACTORY_FOLDERS: tuple[str, ...] = (*_PYTHON_NODE_KIND_FOLDERS, "factories")
_PYTHON_NODE_KIND_BY_FOLDER: dict[str, str] = {
    "loaders": "loader",
    "tasks": "task",
    "assets": "asset",
    "checks": "check",
}


@dataclass
class _PythonNodeDiscoveryBucket:
    loaders: list[DiscoveredLoaderFunction] = field(default_factory=list)
    tasks: list[DiscoveredTaskFunction] = field(default_factory=list)
    assets: list[DiscoveredAssetFunction] = field(default_factory=list)
    checks: list[DiscoveredCheckFunction] = field(default_factory=list)
    audit_factories: list[DiscoveredAuditFactory] = field(default_factory=list)

    def add_loader(self, item: DiscoveredLoaderFunction) -> None:
        self.loaders.append(item)

    def add_task(self, item: DiscoveredTaskFunction) -> None:
        self.tasks.append(item)

    def add_asset(self, item: DiscoveredAssetFunction) -> None:
        self.assets.append(item)

    def add_check(self, item: DiscoveredCheckFunction) -> None:
        self.checks.append(item)

    def add_audit_factory(self, item: DiscoveredAuditFactory) -> None:
        self.audit_factories.append(item)


@dataclass(frozen=True)
class _DeclarationFileFacts:
    file_path: Path
    relative_path: Path
    declaration_kind: DeclarationKind
    scope_kind: ScopeKind
    ownership_root: Path
    owning_path: Path | None
    declaration_root: Path


_SCOPED_DECLARATION_DIRECTORIES: frozenset[str] = (
    INHERITED_DECLARATION_DIRECTORIES | LOCAL_DECLARATION_DIRECTORIES
)


def _discover_declaration_file_facts(
    *, project_dir: Path, declaration_kind: DeclarationKind | None = None
) -> tuple[_DeclarationFileFacts, ...]:
    for directory_name in sorted(LOCAL_DECLARATION_DIRECTORIES):
        directory_kind, _scope_kind = DECLARATION_DIRECTORY_FACTS[directory_name]
        if (declaration_kind is None or directory_kind is declaration_kind) and (
            project_dir / directory_name
        ).is_dir():
            raise DeclarationParseError(
                f"Scoped declaration root {directory_name}/ must be below a canonical authored root"
            )

    facts: list[_DeclarationFileFacts] = []
    global_directory: str
    for global_directory in sorted(GLOBAL_DECLARATION_DIRECTORIES):
        directory_kind, _scope_kind = DECLARATION_DIRECTORY_FACTS[global_directory]
        if declaration_kind is not None and directory_kind is not declaration_kind:
            continue
        declaration_root: Path = project_dir / global_directory
        if declaration_root.is_dir():
            facts.extend(
                _declaration_files_under_root(
                    project_dir=project_dir,
                    ownership_root=Path(global_directory),
                    declaration_root=declaration_root,
                    owning_path=None,
                    scope_kind=ScopeKind.GLOBAL,
                )
            )

    root_components: tuple[str, ...]
    for root_components in CANONICAL_AUTHORED_ROOTS:
        authored_root: Path = project_dir.joinpath(*root_components)
        if not authored_root.is_dir():
            continue
        directory: Path
        for directory in sorted(path for path in authored_root.rglob("*") if path.is_dir()):
            if directory.name not in _SCOPED_DECLARATION_DIRECTORIES:
                continue
            directory_kind, directory_scope_kind = DECLARATION_DIRECTORY_FACTS[directory.name]
            if declaration_kind is not None and directory_kind is not declaration_kind:
                continue
            relative_directory: Path = directory.relative_to(project_dir)
            descendants: tuple[str, ...] = relative_directory.parts[len(root_components) :]
            if any(part in _SCOPED_DECLARATION_DIRECTORIES for part in descendants[:-1]):
                raise DeclarationParseError(
                    f"Declaration root {relative_directory.as_posix()}/ is nested inside another "
                    "declaration tree"
                )
            facts.extend(
                _declaration_files_under_root(
                    project_dir=project_dir,
                    ownership_root=Path(*root_components),
                    declaration_root=directory,
                    owning_path=relative_directory.parent,
                    scope_kind=directory_scope_kind,
                )
            )
    return tuple(sorted(facts, key=lambda item: item.relative_path.as_posix()))


def _declaration_files_under_root(
    *,
    project_dir: Path,
    ownership_root: Path,
    declaration_root: Path,
    owning_path: Path | None,
    scope_kind: ScopeKind,
) -> list[_DeclarationFileFacts]:
    nested_root: Path
    for nested_root in sorted(
        path
        for path in declaration_root.rglob("*")
        if path.is_dir() and path.name in _SCOPED_DECLARATION_DIRECTORIES
    ):
        relative_nested_root: str = nested_root.relative_to(project_dir).as_posix()
        raise DeclarationParseError(
            f"Declaration root {relative_nested_root}/ is nested inside another declaration tree"
        )
    declaration_kind: DeclarationKind = DECLARATION_DIRECTORY_FACTS[declaration_root.name][0]
    suffix: str = ".py" if declaration_kind is DeclarationKind.MACRO else ".sql"
    results: list[_DeclarationFileFacts] = []
    file_path: Path
    for file_path in sorted(declaration_root.rglob(f"*{suffix}")):
        if declaration_kind is DeclarationKind.MACRO and file_path.stem == PYTHON_INIT_MODULE_STEM:
            continue
        results.append(
            _DeclarationFileFacts(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                declaration_kind=declaration_kind,
                scope_kind=scope_kind,
                ownership_root=ownership_root,
                owning_path=owning_path,
                declaration_root=declaration_root.relative_to(project_dir),
            )
        )
    return results


def _is_in_scoped_declaration_tree(*, file_path: Path, project_dir: Path) -> bool:
    relative_parts: tuple[str, ...] = file_path.relative_to(project_dir).parts
    root_components: tuple[str, ...]
    for root_components in CANONICAL_AUTHORED_ROOTS:
        if relative_parts[: len(root_components)] != root_components:
            continue
        return any(
            component in _SCOPED_DECLARATION_DIRECTORIES
            for component in relative_parts[len(root_components) : -1]
        )
    return False


def discover_model_files(
    *,
    project_dir: Path,
    extract_implicit_alias_columns: bool = True,
    extract_output_column_locations: bool = True,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
) -> tuple[DiscoveredSqlModelFile, ...]:
    """Discover SQL model files under models/."""

    model_root: Path = project_dir / "models"
    if not model_root.is_dir():
        return ()

    discovered_model_files: list[DiscoveredSqlModelFile] = []
    file_path: Path
    for file_path in sorted(model_root.rglob("*.sql")):
        if _is_in_scoped_declaration_tree(file_path=file_path, project_dir=project_dir):
            continue
        try:
            discovered_model_files.append(
                _discover_model_file(
                    project_dir=project_dir,
                    file_path=file_path,
                    extract_implicit_alias_columns=extract_implicit_alias_columns,
                    extract_output_column_locations=extract_output_column_locations,
                )
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
    return tuple(discovered_model_files)


def _discover_model_file(
    *,
    project_dir: Path,
    file_path: Path,
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
) -> DiscoveredSqlModelFile:
    contents: str = file_path.read_text(encoding="utf-8")
    header_values, query_sql = parse_model_sql(contents=contents, file_path=file_path)
    relative_path: Path = file_path.relative_to(project_dir)
    return DiscoveredSqlModelFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        header_values=header_values,
        header_column_locations=model_header_column_locations(
            contents=contents, relative_path=relative_path
        ),
        output_column_locations=(
            model_output_column_locations(
                contents=contents,
                relative_path=relative_path,
                extract_implicit_alias_columns=extract_implicit_alias_columns,
            )
            if extract_output_column_locations
            else {}
        ),
        query_sql=query_sql,
        enum_declarations=parse_model_enum_declarations(
            raw_value=header_values.get("enums"),
            model_name=file_path.stem,
            relative_path=relative_path,
        ),
        constant_declarations=parse_model_constant_declarations(
            raw_value=header_values.get("constants"),
            model_name=file_path.stem,
            relative_path=relative_path,
        ),
        output_column_locations_extracted=extract_output_column_locations,
        extract_implicit_alias_columns=extract_implicit_alias_columns,
    )


def discover_enum_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
    isolate_declaration_kind: bool = False,
) -> tuple[DiscoveredEnumFile, ...]:
    """Discover global and scoped enum declaration files."""

    discovered_files: list[DiscoveredEnumFile] = []
    facts: _DeclarationFileFacts
    for facts in _discover_declaration_file_facts(
        project_dir=project_dir,
        declaration_kind=DeclarationKind.ENUM if isolate_declaration_kind else None,
    ):
        if facts.declaration_kind is not DeclarationKind.ENUM:
            continue
        try:
            contents: str = facts.file_path.read_text(encoding="utf-8")
            declarations: tuple[EnumDeclaration, ...] = parse_enum_declaration_file(
                contents=contents,
                file_path=facts.file_path,
                relative_path=facts.relative_path,
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=facts.file_path, error=error))
            continue
        discovered_files.append(
            DiscoveredEnumFile(
                file_path=facts.file_path,
                relative_path=facts.relative_path,
                contents=contents,
                declarations=declarations,
                scope_kind=facts.scope_kind,
                ownership_root=facts.ownership_root,
                owning_path=facts.owning_path,
                declaration_root=facts.declaration_root,
            )
        )
    return tuple(discovered_files)


def discover_constant_files(
    *,
    project_dir: Path,
    on_fault: Callable[[DiscoveryFileFault], None] | None = None,
    isolate_declaration_kind: bool = False,
) -> tuple[DiscoveredConstantFile, ...]:
    """Discover global and scoped constant declaration files."""

    discovered_files: list[DiscoveredConstantFile] = []
    facts: _DeclarationFileFacts
    for facts in _discover_declaration_file_facts(
        project_dir=project_dir,
        declaration_kind=DeclarationKind.CONSTANT if isolate_declaration_kind else None,
    ):
        if facts.declaration_kind is not DeclarationKind.CONSTANT:
            continue
        try:
            contents: str = facts.file_path.read_text(encoding="utf-8")
            declarations: tuple[ConstantDeclaration, ...] = parse_constant_declaration_file(
                contents=contents,
                file_path=facts.file_path,
                relative_path=facts.relative_path,
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=facts.file_path, error=error))
            continue
        discovered_files.append(
            DiscoveredConstantFile(
                file_path=facts.file_path,
                relative_path=facts.relative_path,
                contents=contents,
                declarations=declarations,
                scope_kind=facts.scope_kind,
                ownership_root=facts.ownership_root,
                owning_path=facts.owning_path,
                declaration_root=facts.declaration_root,
            )
        )
    return tuple(discovered_files)


def discover_model_schema_files(*, project_dir: Path) -> tuple[DiscoveredModelSchemaFile, ...]:
    """Discover public reusable model schemas under schemas/."""

    schema_root: Path = project_dir / MODEL_SCHEMAS_DIRECTORY_NAME
    if not schema_root.is_dir():
        return ()
    discovered_files: list[DiscoveredModelSchemaFile] = []
    file_path: Path
    for file_path in sorted(schema_root.rglob("*.sql")):
        contents: str = file_path.read_text(encoding="utf-8")
        relative_path: Path = file_path.relative_to(project_dir)
        discovered_files.append(
            DiscoveredModelSchemaFile(
                file_path=file_path,
                relative_path=relative_path,
                contents=contents,
                declarations=parse_model_schema_declaration_file(
                    contents=contents,
                    file_path=file_path,
                    relative_path=relative_path,
                ),
            )
        )
    return tuple(discovered_files)


def discover_sql_function_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlFunctionFile, ...]:
    """Discover SQL function files under functions/sql/."""

    function_root: Path = project_dir / "functions" / "sql"
    if not function_root.is_dir():
        return ()

    discovered_function_files: list[DiscoveredSqlFunctionFile] = []
    file_path: Path
    for file_path in sorted(function_root.rglob("*.sql")):
        if _is_in_scoped_declaration_tree(file_path=file_path, project_dir=project_dir):
            continue
        try:
            contents: str = file_path.read_text(encoding="utf-8")
            header_values: dict[str, object]
            body_sql: str
            header_values, body_sql = parse_function_sql(contents=contents, file_path=file_path)
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
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
        header_values, entry_point, body_python = parse_python_function(
            contents=contents, file_path=file_path
        )
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
        schema_paths.extend(
            path
            for path in sorted(models_root.rglob(SCHEMA_FILE_NAME))
            if not _is_in_scoped_declaration_tree(file_path=path, project_dir=project_dir)
        )
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
        model_entries, seed_entries = parse_schema_yml(contents=contents, file_path=file_path)
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


def discover_source_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSourceFile, ...]:
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
        try:
            contents: str = file_path.read_text(encoding="utf-8")
            source_entries: tuple[SourceEntry, ...] = parse_sources_yml(
                contents=contents, file_path=file_path
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
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


def discover_test_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlTestFile, ...]:
    """Discover SQL-native unit test files under tests/unit/."""

    tests_root: Path = project_dir / "tests" / "unit"
    if not tests_root.is_dir():
        return ()

    discovered_test_files: list[DiscoveredSqlTestFile] = []
    file_path: Path
    for file_path in sorted(tests_root.rglob("*.sql")):
        if _is_in_scoped_declaration_tree(file_path=file_path, project_dir=project_dir):
            continue
        try:
            contents: str = file_path.read_text(encoding="utf-8")
            blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
                contents=contents, file_path=file_path
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
        discovered_test_files.append(
            DiscoveredSqlTestFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=contents,
                blocks=blocks,
                ownership_root=Path(SQL_TESTS_OWNERSHIP_ROOT),
            )
        )
    return tuple(discovered_test_files)


def discover_scenario_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlScenarioFile, ...]:
    """Discover SQL-native scenario files under tests/scenarios/."""

    scenarios_root: Path = project_dir / "tests" / "scenarios"
    if not scenarios_root.is_dir():
        return ()

    discovered_scenario_files: list[DiscoveredSqlScenarioFile] = []
    file_path: Path
    for file_path in sorted(scenarios_root.rglob("*.sql")):
        if _is_in_scoped_declaration_tree(file_path=file_path, project_dir=project_dir):
            continue
        try:
            contents: str = file_path.read_text(encoding="utf-8")
            scenario: DiscoveredSqlScenarioFile = parse_sql_scenario_file(
                contents=contents,
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
        discovered_scenario_files.append(scenario)
    return tuple(discovered_scenario_files)


def discover_audit_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredAuditFile, ...]:
    """Discover audit SQL files under audits/."""

    audits_root: Path = project_dir / "audits"
    if not audits_root.is_dir():
        return ()

    discovered_audit_files: list[DiscoveredAuditFile] = []
    file_path: Path
    for file_path in sorted(audits_root.rglob("*.sql")):
        if _is_in_scoped_declaration_tree(file_path=file_path, project_dir=project_dir):
            continue
        try:
            contents: str = file_path.read_text(encoding="utf-8")
            discovered_audit_files.append(
                DiscoveredAuditFile(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    contents=contents,
                    blocks=parse_sql_audit_file(contents=contents, file_path=file_path),
                )
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
    return tuple(discovered_audit_files)


def discover_macro_files(
    *, project_dir: Path, isolate_declaration_kind: bool = False
) -> tuple[DiscoveredMacroFile, ...]:
    """Discover global and scoped project macro Python files."""

    return tuple(
        DiscoveredMacroFile(
            file_path=facts.file_path,
            relative_path=facts.relative_path,
            contents=facts.file_path.read_text(encoding="utf-8"),
            scope_kind=facts.scope_kind,
            ownership_root=facts.ownership_root,
            owning_path=facts.owning_path,
            declaration_root=facts.declaration_root,
        )
        for facts in _discover_declaration_file_facts(
            project_dir=project_dir,
            declaration_kind=DeclarationKind.MACRO if isolate_declaration_kind else None,
        )
        if facts.declaration_kind is DeclarationKind.MACRO
    )


def _discovery_fault(*, project_dir: Path, path: Path, error: Exception) -> DiscoveryFileFault:
    try:
        relative_path: Path | None = path.relative_to(project_dir)
    except ValueError:
        relative_path = None
    message: str = str(error).replace(str(project_dir), ".")
    return DiscoveryFileFault(path=relative_path, message=message)


def discover_materialization_files(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredMaterializationFile, ...]:
    """Discover custom materialization Python files under materializations/."""

    materializations_root: Path = project_dir / "materializations"
    if not materializations_root.is_dir():
        return ()

    provider_by_name: dict[str, DiscoveredProvider] = _provider_by_name(providers)
    discovered_files: list[DiscoveredMaterializationFile] = []
    file_path: Path
    for file_path in sorted(materializations_root.rglob("*.py")):
        if file_path.stem == PYTHON_INIT_MODULE_STEM:
            continue
        materialize_fn: Callable[..., object] | None = _load_materialize_function(
            file_path=file_path,
            project_dir=project_dir,
        )
        discovered_files.append(
            DiscoveredMaterializationFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                name=file_path.stem,
                provider_usages=(
                    _provider_usages(function=materialize_fn, provider_by_name=provider_by_name)
                    if materialize_fn is not None
                    else ()
                ),
            )
        )
    return tuple(discovered_files)


def discover_loader_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Discover decorated source loader functions under loaders/."""

    return tuple(
        _discover_python_node_functions(project_dir=project_dir, providers=providers).loaders
    )


def discover_task_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredTaskFunction, ...]:
    """Discover decorated task functions under tasks/."""

    return tuple(
        _discover_python_node_functions(project_dir=project_dir, providers=providers).tasks
    )


def discover_asset_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredAssetFunction, ...]:
    """Discover decorated asset functions under assets/."""

    return tuple(
        _discover_python_node_functions(project_dir=project_dir, providers=providers).assets
    )


def discover_check_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredCheckFunction, ...]:
    """Discover decorated check functions under checks/."""

    return tuple(
        _discover_python_node_functions(project_dir=project_dir, providers=providers).checks
    )


def discover_python_node_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> DiscoveredPythonNodeFunctions:
    """Discover decorated Python DAG node functions under node folders."""

    bucket: _PythonNodeDiscoveryBucket = _discover_python_node_functions(
        project_dir=project_dir,
        providers=providers,
    )
    return DiscoveredPythonNodeFunctions(
        loaders=tuple(bucket.loaders),
        tasks=tuple(bucket.tasks),
        assets=tuple(bucket.assets),
        checks=tuple(bucket.checks),
        audit_factories=tuple(bucket.audit_factories),
    )


def discover_hook_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredHookFunction, ...]:
    """Discover decorated model lifecycle hook functions under hooks/python/."""

    hooks_root: Path = project_dir / "hooks" / "python"
    if not hooks_root.is_dir():
        return ()

    discovered_hooks: list[DiscoveredHookFunction] = []
    seen_names: dict[str, Path] = {}
    provider_by_name: dict[str, DiscoveredProvider] = _provider_by_name(providers)
    file_path: Path
    for file_path in sorted(hooks_root.rglob("*.py")):
        if file_path.stem == PYTHON_INIT_MODULE_STEM or file_path.name.startswith("_"):
            continue
        module: ModuleType = _load_python_node_module(
            file_path=file_path,
            project_dir=project_dir,
            node_folder="hooks/python",
        )
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            hook_definition: HookDefinition | None = read_hook_definition(value)
            if hook_definition is None:
                continue
            existing_path: Path | None = seen_names.get(hook_definition.name)
            if existing_path is not None:
                raise PythonNodeDiscoveryError(
                    f"Duplicate hook name '{hook_definition.name}' found in "
                    f"{existing_path.relative_to(project_dir)} and "
                    f"{file_path.relative_to(project_dir)}"
                )
            seen_names[hook_definition.name] = file_path
            discovered_hooks.append(
                DiscoveredHookFunction(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=hook_definition.name,
                    function=value,
                    description=hook_definition.description,
                    provider_usages=_provider_usages(
                        function=value,
                        provider_by_name=provider_by_name,
                    ),
                )
            )
    return tuple(discovered_hooks)


def discover_sql_hook_files(
    *, project_dir: Path, on_fault: Callable[[DiscoveryFileFault], None] | None = None
) -> tuple[DiscoveredSqlHookFile, ...]:
    """Discover named SQL lifecycle hook resources under hooks/sql/."""

    hooks_root: Path = project_dir / "hooks" / "sql"
    if not hooks_root.is_dir():
        return ()

    discovered_hooks: list[DiscoveredSqlHookFile] = []
    file_path: Path
    for file_path in sorted(hooks_root.rglob("*.sql")):
        if file_path.name.startswith("_") or _is_in_scoped_declaration_tree(
            file_path=file_path, project_dir=project_dir
        ):
            continue
        try:
            relative_path: Path = file_path.relative_to(project_dir)
            contents: str = file_path.read_text(encoding="utf-8")
            discovered_hooks.append(
                parse_sql_hook_file(
                    contents=contents,
                    file_path=file_path,
                    relative_path=relative_path,
                )
            )
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(_discovery_fault(project_dir=project_dir, path=file_path, error=error))
            continue
    return tuple(discovered_hooks)


def discover_provider_classes(*, project_dir: Path) -> tuple[DiscoveredProvider, ...]:
    """Discover provider classes under providers/."""

    from sqlbuild.runtime.event_exporting.main.cached_event_exporter_extensions import (
        cached_event_exporter_extensions,
    )

    cached: (
        tuple[
            tuple[DiscoveredProvider, ...],
            tuple[DiscoveredEventExporter, ...],
            tuple[DiscoveredCommandOutputSink, ...],
        ]
        | None
    ) = cached_event_exporter_extensions(project_dir=project_dir)
    if cached is not None:
        return cached[0]
    providers_root: Path = project_dir / "providers"
    if not providers_root.is_dir():
        return ()

    discovered_providers: list[DiscoveredProvider] = []
    seen_names: dict[str, Path] = {}
    file_path: Path
    for file_path in _public_python_files(root=providers_root):
        module: ModuleType = _load_provider_module(file_path=file_path, project_dir=project_dir)
        for _, value in inspect.getmembers(module, inspect.isclass):
            if value.__module__ != module.__name__:
                continue
            if value is Provider or not issubclass(value, Provider) or inspect.isabstract(value):
                continue
            provider_class: type[Provider] = value
            provider_name: str = _provider_name(
                provider_class=provider_class,
                file_path=file_path,
                project_dir=project_dir,
            )
            existing_path: Path | None = seen_names.get(provider_name)
            if existing_path is not None:
                raise ProviderDiscoveryError(
                    f"Duplicate provider name '{provider_name}' found in "
                    f"{existing_path.relative_to(project_dir)} and "
                    f"{file_path.relative_to(project_dir)}"
                )
            seen_names[provider_name] = file_path
            discovered_providers.append(
                DiscoveredProvider(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=provider_name,
                    provider_class=provider_class,
                    settings=_provider_instance(
                        provider_class=provider_class,
                        provider_name=provider_name,
                        file_path=file_path,
                        project_dir=project_dir,
                    ),
                )
            )
    return tuple(discovered_providers)


def discover_event_exporter_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> tuple[DiscoveredEventExporter, ...]:
    """Discover validated lifecycle-event sink declarations under sinks/."""

    from sqlbuild.runtime.event_exporting.main.cached_event_exporter_extensions import (
        cached_event_exporter_extensions,
    )

    cached: (
        tuple[
            tuple[DiscoveredProvider, ...],
            tuple[DiscoveredEventExporter, ...],
            tuple[DiscoveredCommandOutputSink, ...],
        ]
        | None
    ) = cached_event_exporter_extensions(project_dir=project_dir)
    if cached is not None:
        return cached[1]
    declarations: tuple[DiscoveredEventExporterDeclaration, ...] = (
        discover_event_exporter_declarations(project_dir=project_dir)
    )
    return bind_event_exporter_declarations(
        declarations=declarations,
        providers=providers,
        project_dir=project_dir,
    )


def discover_event_exporter_declarations(
    *, project_dir: Path
) -> tuple[DiscoveredEventExporterDeclaration, ...]:
    """Import sink modules and collect lifecycle declarations without discovering providers."""

    if (project_dir / "event_exporters").exists():
        raise EventExporterDiscoveryError(
            "event_exporters/ was replaced by sinks/ and @lifecycle_event_sink"
        )
    exporters_root: Path = project_dir / "sinks"
    if not exporters_root.is_dir():
        return ()
    discovered: list[DiscoveredEventExporterDeclaration] = []
    seen_names: dict[str, Path] = {}
    for file_path in _public_python_files(root=exporters_root):
        module: ModuleType = _load_sink_module(file_path=file_path, project_dir=project_dir)
        seen_function_ids: set[int] = set()
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            function_id: int = id(value)
            if function_id in seen_function_ids:
                continue
            seen_function_ids.add(function_id)
            definition: LifecycleEventSinkDefinition | None = get_lifecycle_event_sink_definition(
                value
            )
            if definition is None:
                continue
            existing_path: Path | None = seen_names.get(definition.name)
            if existing_path is not None:
                raise EventExporterDiscoveryError(
                    f"Duplicate event exporter name '{definition.name}' found in "
                    f"{existing_path.relative_to(project_dir)} and "
                    f"{file_path.relative_to(project_dir)}"
                )
            _validate_event_exporter_declaration_signature(
                function=value,
                exporter_name=definition.name,
                file_path=file_path,
                project_dir=project_dir,
            )
            seen_names[definition.name] = file_path
            discovered.append(
                DiscoveredEventExporterDeclaration(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=definition.name,
                    function=value,
                    event_kinds=definition.event_kinds,
                    min_severity=definition.min_severity,
                )
            )
    return tuple(discovered)


def bind_event_exporter_declarations(
    *,
    declarations: tuple[DiscoveredEventExporterDeclaration, ...],
    providers: tuple[DiscoveredProvider, ...],
    project_dir: Path,
) -> tuple[DiscoveredEventExporter, ...]:
    """Validate declaration provider parameters against discovered project providers."""

    provider_by_name: dict[str, DiscoveredProvider] = _provider_by_name(providers)
    bound: list[DiscoveredEventExporter] = []
    for declaration in declarations:
        usages: tuple[DiscoveredProviderUsage, ...] = _bind_event_exporter_provider_usages(
            function=declaration.function,
            exporter_name=declaration.name,
            file_path=declaration.file_path,
            project_dir=project_dir,
            provider_by_name=provider_by_name,
        )
        bound.append(
            DiscoveredEventExporter(
                file_path=declaration.file_path,
                relative_path=declaration.relative_path,
                name=declaration.name,
                function=declaration.function,
                event_kinds=declaration.event_kinds,
                min_severity=declaration.min_severity,
                provider_usages=usages,
            )
        )
    return tuple(bound)


def _validate_event_exporter_declaration_signature(
    *,
    function: Callable[..., object],
    exporter_name: str,
    file_path: Path,
    project_dir: Path,
) -> None:
    relative_path: Path = file_path.relative_to(project_dir)
    if inspect.iscoroutinefunction(function):
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} must be synchronous"
        )
    parameters: tuple[inspect.Parameter, ...] = tuple(
        inspect.signature(function).parameters.values()
    )
    if not parameters or parameters[0].name != EVENT_EXPORTER_EVENT_PARAMETER_NAME:
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} must declare event first"
        )
    if any(
        parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }
        for parameter in parameters
    ):
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} must use named parameters"
        )
    if any(parameter.default is not inspect.Parameter.empty for parameter in parameters):
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} parameters must not have defaults"
        )
    try:
        type_hints: dict[str, object] = get_type_hints(function)
    except (NameError, TypeError) as error:
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} has invalid annotations"
        ) from error
    event_annotation: object = type_hints.get("event", parameters[0].annotation)
    if event_annotation not in {inspect.Parameter.empty, LifecycleEvent}:
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} event must be LifecycleEvent"
        )
    return_annotation: object = type_hints.get(
        "return", inspect.signature(function).return_annotation
    )
    if return_annotation not in {inspect.Signature.empty, None, type(None)}:
        raise EventExporterDiscoveryError(
            f"Event exporter '{exporter_name}' in {relative_path} return annotation must be None"
        )


def _bind_event_exporter_provider_usages(
    *,
    function: Callable[..., object],
    exporter_name: str,
    file_path: Path,
    project_dir: Path,
    provider_by_name: dict[str, DiscoveredProvider],
) -> tuple[DiscoveredProviderUsage, ...]:
    relative_path: Path = file_path.relative_to(project_dir)
    parameters: tuple[inspect.Parameter, ...] = tuple(
        inspect.signature(function).parameters.values()
    )
    type_hints: dict[str, object] = get_type_hints(function)
    for parameter in parameters[1:]:
        provider: DiscoveredProvider | None = provider_by_name.get(parameter.name)
        if provider is None:
            raise EventExporterDiscoveryError(
                f"Event exporter '{exporter_name}' in {relative_path} requires unknown provider "
                f"'{parameter.name}'"
            )
        annotation: object = type_hints.get(parameter.name, parameter.annotation)
        if annotation is not inspect.Parameter.empty and annotation is not provider.provider_class:
            provider_class_name: str = provider.provider_class.__name__
            raise EventExporterDiscoveryError(
                f"Event exporter '{exporter_name}' in {relative_path} provider parameter "
                f"'{parameter.name}' must be unannotated or exactly {provider_class_name}"
            )
    return _provider_usages(function=function, provider_by_name=provider_by_name)


def _public_python_files(*, root: Path) -> tuple[Path, ...]:
    public_files: list[Path] = []
    for file_path in sorted(root.rglob("*.py")):
        relative_parts: tuple[str, ...] = file_path.relative_to(root).parts
        if file_path.stem == PYTHON_INIT_MODULE_STEM:
            continue
        if any(part.startswith("_") for part in relative_parts):
            continue
        public_files.append(file_path)
    return tuple(public_files)


def _provider_name(*, provider_class: type[Provider], file_path: Path, project_dir: Path) -> str:
    relative_path: Path = file_path.relative_to(project_dir)
    explicit_name: str | None = provider_class.provider_name
    if explicit_name is not None:
        validate_resource_identity(
            name=explicit_name,
            kind="provider",
            path=relative_path,
        )
    try:
        provider_name: str = provider_class.name()
    except ProviderInputError as error:
        raise ProviderDiscoveryError(
            f"Provider class {provider_class.__name__} in {relative_path} "
            f"has an invalid provider name: {error}"
        ) from error
    validate_resource_identity(
        name=provider_name,
        kind="provider",
        path=relative_path,
    )
    return provider_name


def _provider_instance(
    *, provider_class: type[Provider], provider_name: str, file_path: Path, project_dir: Path
) -> Provider:
    try:
        return provider_class()
    except ValidationError as error:
        relative_path: Path = file_path.relative_to(project_dir)
        raise ProviderDiscoveryError(
            f"Provider '{provider_name}' in {relative_path} has invalid settings:\n"
            f"{_format_provider_validation_error(error)}"
        ) from error


def _format_provider_validation_error(error: ValidationError) -> str:
    details: list[str] = []
    for item in error.errors(include_input=False):
        location: object = item.get("loc", ())
        location_text: str = ".".join(str(part) for part in location) if location else "<root>"
        message: object = item.get("msg", "invalid value")
        error_type: object = item.get("type", "validation_error")
        details.append(f"{location_text}: {message} [{error_type}]")
    return "\n".join(details) or "invalid provider settings"


def _provider_by_name(providers: tuple[DiscoveredProvider, ...]) -> dict[str, DiscoveredProvider]:
    return {provider.name: provider for provider in providers}


def _provider_usages(
    *, function: Callable[..., object], provider_by_name: dict[str, DiscoveredProvider]
) -> tuple[DiscoveredProviderUsage, ...]:
    try:
        type_hints: dict[str, object] = get_type_hints(function)
    except TypeError:
        type_hints = {}
    usages: list[DiscoveredProviderUsage] = []
    parameter: inspect.Parameter
    for parameter in inspect.signature(function).parameters.values():
        discovered_provider: DiscoveredProvider | None = provider_by_name.get(parameter.name)
        if discovered_provider is None:
            continue
        annotation: object = type_hints.get(parameter.name, parameter.annotation)
        annotation_class_name: str | None = None
        annotation_module: str | None = None
        if isinstance(annotation, type) and issubclass(annotation, Provider):
            annotation_class_name = annotation.__name__
            annotation_module = annotation.__module__
        usages.append(
            DiscoveredProviderUsage(
                provider_name=discovered_provider.name,
                parameter_name=parameter.name,
                annotation_class_name=annotation_class_name,
                annotation_module=annotation_module,
            )
        )
    return tuple(usages)


def _load_materialize_function(
    *, file_path: Path, project_dir: Path
) -> Callable[..., object] | None:
    module: ModuleType = _load_materialization_module(
        file_path=file_path,
        project_dir=project_dir,
    )
    materialize_fn: object = getattr(module, "materialize", None)
    return materialize_fn if callable(materialize_fn) else None


def _discover_python_node_functions(
    *, project_dir: Path, providers: tuple[DiscoveredProvider, ...] = ()
) -> _PythonNodeDiscoveryBucket:
    bucket: _PythonNodeDiscoveryBucket = _PythonNodeDiscoveryBucket()
    provider_by_name: dict[str, DiscoveredProvider] = _provider_by_name(providers)
    node_folder: str
    for node_folder in _PYTHON_NODE_FACTORY_FOLDERS:
        node_root: Path = project_dir / node_folder
        if not node_root.is_dir():
            continue
        file_path: Path
        for file_path in sorted(node_root.rglob("*.py")):
            if file_path.stem == PYTHON_INIT_MODULE_STEM:
                continue
            module: ModuleType = (
                _load_loader_module(file_path=file_path, project_dir=project_dir)
                if node_folder == PYTHON_LOADER_FOLDER
                else _load_python_node_module(
                    file_path=file_path,
                    project_dir=project_dir,
                    node_folder=node_folder,
                )
            )
            _append_module_python_nodes(
                bucket=bucket,
                module=module,
                file_path=file_path,
                project_dir=project_dir,
                node_folder=node_folder,
                provider_by_name=provider_by_name,
            )
    return bucket


def _append_module_python_nodes(
    *,
    bucket: _PythonNodeDiscoveryBucket,
    module: ModuleType,
    file_path: Path,
    project_dir: Path,
    node_folder: str,
    provider_by_name: dict[str, DiscoveredProvider],
) -> None:
    _append_module_audit_factories(
        bucket=bucket,
        module=module,
        file_path=file_path,
        project_dir=project_dir,
        node_folder=node_folder,
    )
    if node_folder != PYTHON_FACTORY_FOLDER:
        for _, value in inspect.getmembers(module, inspect.isfunction):
            if value.__module__ != module.__name__:
                continue
            _append_python_node_function(
                bucket=bucket,
                function=value,
                file_path=file_path,
                project_dir=project_dir,
                expected_kind=_PYTHON_NODE_KIND_BY_FOLDER.get(node_folder),
                provider_by_name=provider_by_name,
            )
    for _, value in inspect.getmembers(module, inspect.isfunction):
        if value.__module__ != module.__name__:
            continue
        factory_definition: FactoryDefinition | None = read_factory_definition(value)
        if factory_definition is None:
            continue
        generated_functions: tuple[Callable[..., object], ...] = _call_factory(
            factory=value,
            factory_definition=factory_definition,
            file_path=file_path,
            project_dir=project_dir,
        )
        index: int
        generated_function: Callable[..., object]
        for index, generated_function in enumerate(generated_functions):
            if not _append_python_node_function(
                bucket=bucket,
                function=generated_function,
                file_path=file_path,
                project_dir=project_dir,
                expected_kind=_PYTHON_NODE_KIND_BY_FOLDER.get(node_folder),
                factory_definition=factory_definition,
                provider_by_name=provider_by_name,
            ):
                raise PythonNodeDiscoveryError(
                    f"Factory '{factory_definition.name}' in "
                    f"{file_path.relative_to(project_dir)} returned item {index} that is not "
                    "a SQLBuild task, asset, loader, or check"
                )


def _append_module_audit_factories(
    *,
    bucket: _PythonNodeDiscoveryBucket,
    module: ModuleType,
    file_path: Path,
    project_dir: Path,
    node_folder: str,
) -> None:
    """Collect audit factories without routing them through Python-node discovery."""

    for _, value in inspect.getmembers(module, inspect.isfunction):
        if value.__module__ != module.__name__:
            continue
        definition: AuditFactoryDefinition | None = read_audit_factory_definition(value)
        if definition is None:
            continue
        relative_path: Path = file_path.relative_to(project_dir)
        if node_folder != PYTHON_FACTORY_FOLDER:
            raise PythonNodeDiscoveryError(
                f"Audit factory '{definition.name}' in {relative_path} must live under factories/"
            )
        if _python_node_definition_names(value):
            kinds: str = ", ".join(_python_node_definition_names(value))
            raise PythonNodeDiscoveryError(
                f"Audit factory '{definition.name}' in {relative_path} cannot also be decorated "
                f"as a Python-node kind ({kinds})"
            )
        existing: DiscoveredAuditFactory | None = next(
            (item for item in bucket.audit_factories if item.name == definition.name), None
        )
        if existing is not None:
            raise PythonNodeDiscoveryError(
                f"Duplicate audit factory name '{definition.name}' found in "
                f"{existing.relative_path} and {relative_path}"
            )
        cases: tuple[AuditCase, ...] = _call_audit_factory(
            factory=value,
            definition=definition,
            file_path=file_path,
            project_dir=project_dir,
        )
        bucket.add_audit_factory(
            DiscoveredAuditFactory(
                name=definition.name,
                function=value,
                file_path=file_path,
                relative_path=relative_path,
                line=inspect.getsourcelines(value)[1],
                cases=cases,
            )
        )


def _python_node_definition_names(function: Callable[..., object]) -> tuple[str, ...]:
    definitions: tuple[tuple[str, object | None], ...] = (
        ("factory", read_factory_definition(function)),
        ("loader", read_loader_definition(function)),
        ("task", read_task_definition(function)),
        ("asset", read_asset_definition(function)),
        ("check", read_check_definition(function)),
    )
    return tuple(name for name, definition in definitions if definition is not None)


def _call_audit_factory(
    *,
    factory: Callable[..., object],
    definition: AuditFactoryDefinition,
    file_path: Path,
    project_dir: Path,
) -> tuple[AuditCase, ...]:
    relative_path: Path = file_path.relative_to(project_dir)
    if inspect.signature(factory).parameters:
        raise PythonNodeDiscoveryError(
            f"Audit factory '{definition.name}' in {relative_path} must not require arguments"
        )
    try:
        result: object = factory()
    except Exception as error:
        raise PythonNodeDiscoveryError(
            f"Audit factory '{definition.name}' in {relative_path} failed during discovery: {error}"
        ) from error
    if not isinstance(result, list | tuple):
        raise PythonNodeDiscoveryError(
            f"Audit factory '{definition.name}' in {relative_path} must return a list or tuple "
            "of AuditCase instances"
        )
    cases: list[AuditCase] = []
    for index, item in enumerate(result):
        if not isinstance(item, AuditCase):
            raise PythonNodeDiscoveryError(
                f"Audit factory '{definition.name}' in {relative_path} returned item {index} "
                "that is not an AuditCase"
            )
        cases.append(item)
    return tuple(cases)


def _append_python_node_function(
    *,
    bucket: _PythonNodeDiscoveryBucket,
    function: Callable[..., object],
    file_path: Path,
    project_dir: Path,
    expected_kind: str | None = None,
    factory_definition: FactoryDefinition | None = None,
    provider_by_name: dict[str, DiscoveredProvider] | None = None,
) -> bool:
    resolved_provider_by_name: dict[str, DiscoveredProvider] = provider_by_name or {}
    loader_definition: LoaderDefinition | None = read_loader_definition(function)
    if loader_definition is not None:
        _validate_python_node_kind(
            actual_kind="loader",
            expected_kind=expected_kind,
            function_name=loader_definition.name,
            factory_definition=factory_definition,
            file_path=file_path,
            project_dir=project_dir,
        )
        bucket.add_loader(
            DiscoveredLoaderFunction(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                name=loader_definition.name,
                function=function,
                depends_on=loader_definition.depends_on,
                destination=loader_definition.destination,
                write_strategy=loader_definition.write_strategy,
                cursor_column=loader_definition.cursor_column,
                unique_key=loader_definition.unique_key,
                columns=loader_definition.columns,
                contract=loader_definition.contract,
                provider_usages=_provider_usages(
                    function=function,
                    provider_by_name=resolved_provider_by_name,
                ),
            )
        )
        return True
    task_definition: TaskDefinition | None = read_task_definition(function)
    if task_definition is not None:
        _validate_python_node_kind(
            actual_kind="task",
            expected_kind=expected_kind,
            function_name=task_definition.name,
            factory_definition=factory_definition,
            file_path=file_path,
            project_dir=project_dir,
        )
        bucket.add_task(
            DiscoveredTaskFunction(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                name=task_definition.name,
                function=function,
                depends_on=task_definition.depends_on,
                tags=task_definition.tags,
                group=task_definition.group,
                description=task_definition.description,
                meta=task_definition.meta,
                retry=task_definition.retry,
                provider_usages=_provider_usages(
                    function=function,
                    provider_by_name=resolved_provider_by_name,
                ),
            )
        )
        return True
    asset_definition: AssetDefinition | None = read_asset_definition(function)
    if asset_definition is not None:
        _validate_python_node_kind(
            actual_kind="asset",
            expected_kind=expected_kind,
            function_name=asset_definition.name,
            factory_definition=factory_definition,
            file_path=file_path,
            project_dir=project_dir,
        )
        bucket.add_asset(
            DiscoveredAssetFunction(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                name=asset_definition.name,
                function=function,
                depends_on=asset_definition.depends_on,
                tags=asset_definition.tags,
                group=asset_definition.group,
                description=asset_definition.description,
                meta=asset_definition.meta,
                columns=asset_definition.columns,
                column_lineage=asset_definition.column_lineage,
                retry=asset_definition.retry,
                provider_usages=_provider_usages(
                    function=function,
                    provider_by_name=resolved_provider_by_name,
                ),
            )
        )
        return True
    check_definition: CheckDefinition | None = read_check_definition(function)
    if check_definition is not None:
        _validate_python_node_kind(
            actual_kind="check",
            expected_kind=expected_kind,
            function_name=check_definition.name,
            factory_definition=factory_definition,
            file_path=file_path,
            project_dir=project_dir,
        )
        bucket.add_check(
            DiscoveredCheckFunction(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                name=check_definition.name,
                function=function,
                depends_on=check_definition.depends_on,
                severity=check_definition.severity,
                tags=check_definition.tags,
                group=check_definition.group,
                description=check_definition.description,
                meta=check_definition.meta,
                provider_usages=_provider_usages(
                    function=function,
                    provider_by_name=resolved_provider_by_name,
                ),
            )
        )
        return True
    return False


def _validate_python_node_kind(
    *,
    actual_kind: str,
    expected_kind: str | None,
    function_name: str,
    factory_definition: FactoryDefinition | None,
    file_path: Path,
    project_dir: Path,
) -> None:
    if expected_kind is None or actual_kind == expected_kind:
        return
    relative_path: Path = file_path.relative_to(project_dir)
    folder: str = relative_path.parts[0]
    if factory_definition is None:
        article: str = "an" if actual_kind[0] in PYTHON_NODE_KIND_VOWELS else "a"
        raise PythonNodeDiscoveryError(
            f"Python node '{function_name}' in {folder}/ is {article} {actual_kind}; "
            f"{actual_kind}s must live in {actual_kind}s/ or be generated from factories/."
        )
    raise PythonNodeDiscoveryError(
        f"Factory {factory_definition.name} in {folder}/ returned a {actual_kind} "
        f"'{function_name}'; mixed-kind factories must live in factories/."
    )


def _call_factory(
    *,
    factory: Callable[..., object],
    factory_definition: FactoryDefinition,
    file_path: Path,
    project_dir: Path,
) -> tuple[Callable[..., object], ...]:
    parameters: tuple[inspect.Parameter, ...] = tuple(
        inspect.signature(factory).parameters.values()
    )
    if parameters:
        raise PythonNodeDiscoveryError(
            f"Factory '{factory_definition.name}' in {file_path.relative_to(project_dir)} "
            "must not require arguments"
        )
    try:
        result: object = factory()
    except Exception as error:
        raise PythonNodeDiscoveryError(
            f"Factory '{factory_definition.name}' in {file_path.relative_to(project_dir)} "
            f"failed during discovery: {error}"
        ) from error
    return _normalize_factory_result(
        result=result,
        factory_definition=factory_definition,
        file_path=file_path,
        project_dir=project_dir,
    )


def _normalize_factory_result(
    *,
    result: object,
    factory_definition: FactoryDefinition,
    file_path: Path,
    project_dir: Path,
) -> tuple[Callable[..., object], ...]:
    if callable(result):
        return (result,)
    if isinstance(result, str | bytes | dict) or not isinstance(result, list | tuple | set):
        raise PythonNodeDiscoveryError(
            f"Factory '{factory_definition.name}' in {file_path.relative_to(project_dir)} "
            "must return a SQLBuild node function or a list, tuple, or set of node functions"
        )
    functions: list[Callable[..., object]] = []
    index: int
    item: object
    for index, item in enumerate(result):
        if not callable(item):
            raise PythonNodeDiscoveryError(
                f"Factory '{factory_definition.name}' in {file_path.relative_to(project_dir)} "
                f"returned item {index} that is not a SQLBuild task, asset, loader, or check"
            )
        functions.append(item)
    return tuple(functions)


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


def _load_provider_module(*, file_path: Path, project_dir: Path) -> ModuleType:
    module_name: str = ".".join(file_path.relative_to(project_dir).with_suffix("").parts)
    _evict_stale_project_package_modules(
        root_module=module_name.split(".", maxsplit=1)[0],
        project_dir=project_dir,
    )
    existing_module: ModuleType | None = sys.modules.get(module_name)
    if existing_module is not None:
        existing_file: object = getattr(existing_module, "__file__", None)
        if isinstance(existing_file, str) and Path(existing_file).resolve() == file_path.resolve():
            return existing_module
        sys.modules.pop(module_name, None)
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ProviderDiscoveryError(f"Could not load provider file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise ProviderDiscoveryError(
            f"Failed to import provider file {file_path.relative_to(project_dir)}: {error}"
        ) from error
    finally:
        sys.path = old_path
    return module


def _load_sink_module(*, file_path: Path, project_dir: Path) -> ModuleType:
    module_name: str = ".".join(file_path.relative_to(project_dir).with_suffix("").parts)
    _evict_stale_project_package_modules(
        root_module=module_name.split(".", maxsplit=1)[0],
        project_dir=project_dir,
    )
    existing_module: ModuleType | None = sys.modules.get(module_name)
    if existing_module is not None:
        existing_file: object = getattr(existing_module, "__file__", None)
        if isinstance(existing_file, str) and Path(existing_file).resolve() == file_path.resolve():
            return existing_module
        sys.modules.pop(module_name, None)
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise EventExporterDiscoveryError(f"Could not load sink file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise EventExporterDiscoveryError(
            f"Failed to import sink file {file_path.relative_to(project_dir)}: {error}"
        ) from error
    finally:
        sys.path = old_path
    return module


def _evict_stale_project_package_modules(*, root_module: str, project_dir: Path) -> None:
    root_path: Path = (project_dir / root_module).resolve()
    module_name: str
    module: ModuleType
    for module_name, module in tuple(sys.modules.items()):
        if module_name != root_module and not module_name.startswith(f"{root_module}."):
            continue
        module_file: object = getattr(module, "__file__", None)
        if isinstance(module_file, str):
            try:
                Path(module_file).resolve().relative_to(project_dir.resolve())
                continue
            except ValueError:
                sys.modules.pop(module_name, None)
                continue
        module_paths: object = getattr(module, "__path__", None)
        if module_paths is None:
            sys.modules.pop(module_name, None)
            continue
        if any(Path(path).resolve() == root_path for path in module_paths):
            continue
        sys.modules.pop(module_name, None)


def _load_materialization_module(*, file_path: Path, project_dir: Path) -> ModuleType:
    module_name: str = ".".join(file_path.relative_to(project_dir).with_suffix("").parts)
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise PythonNodeDiscoveryError(f"Could not load materialization file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise PythonNodeDiscoveryError(
            f"Failed to import materialization file {file_path.relative_to(project_dir)}: {error}"
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


def _is_relative_to(*, path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
