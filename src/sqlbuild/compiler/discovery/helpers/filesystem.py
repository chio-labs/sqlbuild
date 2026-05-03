"""Filesystem-backed discovery helpers for project inputs."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.helpers.sql_audits import parse_sql_audit_file
from sqlbuild.compiler.discovery.helpers.sql_models import parse_model_sql
from sqlbuild.compiler.discovery.helpers.sql_tests import parse_sql_test_file
from sqlbuild.compiler.discovery.helpers.yml_schema import parse_schema_yml
from sqlbuild.compiler.discovery.helpers.yml_sources import parse_sources_yml
from sqlbuild.compiler.discovery.models import (
    DiscoveredAdapterFile,
    DiscoveredAuditFile,
    DiscoveredDbtManifestFile,
    DiscoveredMacroFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.shared.constants import SCHEMA_FILE_NAME, YAML_FILE_SUFFIXES
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry


def discover_model_files(*, project_dir: Path) -> tuple[DiscoveredSqlModelFile, ...]:
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
                query_sql=query_sql,
            )
        )
    return tuple(discovered_model_files)


def discover_schema_files(*, project_dir: Path) -> tuple[DiscoveredSchemaFile, ...]:
    """Discover schema.yml files under models/ and seeds/."""

    schema_paths: list[Path] = []
    models_root: Path = project_dir / "models"
    seeds_root: Path = project_dir / "seeds"

    if models_root.is_dir():
        schema_paths.extend(sorted(models_root.rglob(SCHEMA_FILE_NAME)))
    if seeds_root.is_dir() and (seeds_root / SCHEMA_FILE_NAME).exists():
        schema_paths.append(seeds_root / SCHEMA_FILE_NAME)

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
    """Discover seed files under seeds/, excluding schema.yml metadata."""

    seeds_root: Path = project_dir / "seeds"
    if not seeds_root.is_dir():
        return ()

    return tuple(
        DiscoveredSeedFile(
            file_path=file_path,
            relative_path=file_path.relative_to(project_dir),
        )
        for file_path in sorted(seeds_root.rglob("*"))
        if file_path.is_file() and file_path.name != SCHEMA_FILE_NAME
    )


def discover_test_files(*, project_dir: Path) -> tuple[DiscoveredSqlTestFile, ...]:
    """Discover SQL-native test files under tests/."""

    tests_root: Path = project_dir / "tests"
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


def discover_dbt_manifest_file(*, project_dir: Path) -> DiscoveredDbtManifestFile | None:
    """Discover an optional dbt manifest.json in common locations."""

    candidate_paths: tuple[Path, ...] = (
        project_dir / "manifest.json",
        project_dir / "target" / "manifest.json",
    )
    for file_path in candidate_paths:
        if file_path.is_file():
            return DiscoveredDbtManifestFile(
                file_path=file_path,
                relative_path=file_path.relative_to(project_dir),
                contents=file_path.read_text(encoding="utf-8"),
            )
    return None


def discover_adapter_file(*, project_dir: Path) -> DiscoveredAdapterFile | None:
    """Detect a project-level adapter.py without importing it."""

    file_path: Path = project_dir / "adapter.py"
    if not file_path.is_file():
        return None

    return DiscoveredAdapterFile(
        file_path=file_path,
        relative_path=file_path.relative_to(project_dir),
    )
