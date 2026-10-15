from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.constants import (
    REMOVED_SQL_MODEL_HEADER_KEYS,
    SQL_MODEL_HEADER_KEYS,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
)
from sqlbuild.spec.contracts.models import (
    SchemaModelEntry,
    SchemaSeedEntry,
    SourceEntry,
    SourceLocation,
)


def write_lifecycle_event_sink_project(*, project_dir: Path, exporter_config: str) -> None:
    (project_dir / "sinks").mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "filters"\nadapter = "duckdb"\n' + exporter_config,
        encoding="utf-8",
    )
    (project_dir / "sinks" / "publish.py").write_text(
        "from sqlbuild.sinks import lifecycle_event_sink\n"
        '@lifecycle_event_sink(event_kinds={"run", "statement"}, min_severity="info")\n'
        "def publish(event):\n    del event\n",
        encoding="utf-8",
    )


def discover_all_model_files(*, project_dir: Path) -> tuple[DiscoveredSqlModelFile, ...]:
    """Discover every model file with the column extraction full compilation uses."""

    return _native.discover_model_files(
        project_dir=project_dir,
        extract_implicit_alias_columns=True,
        extract_output_column_locations=True,
    )


def parse_model_sql(*, contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse model contents as model discovery does, returning header values and query SQL."""

    header_values, query_sql, _ = _parsed_model(contents=contents, file_path=file_path)
    return header_values, query_sql


def model_header_column_locations(
    *, contents: str, relative_path: Path
) -> dict[str, SourceLocation]:
    """Return the authored MODEL(columns) locations model discovery records."""

    return _parsed_model(contents=contents, file_path=relative_path)[2]


def _parsed_model(
    *, contents: str, file_path: Path
) -> tuple[dict[str, object], str, dict[str, SourceLocation]]:
    return _native.parse_model_contents(
        {
            "file_path": str(file_path),
            "supported_keys": sorted(SQL_MODEL_HEADER_KEYS),
            "removed_keys": sorted(REMOVED_SQL_MODEL_HEADER_KEYS),
            "extract_implicit_alias_columns": True,
            "extract_output_column_locations": False,
        },
        contents,
    )


def parse_sql_test_file(*, contents: str, file_path: Path) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse SQL test contents as test discovery does."""

    return _native.parse_sql_test_file(contents=contents, file_path=file_path)


def parse_sql_scenario_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> DiscoveredSqlScenarioFile:
    """Parse scenario contents as scenario discovery does."""

    return _native.parse_sql_scenario_file(
        contents=contents, file_path=file_path, relative_path=relative_path
    )


def parse_sources_yml(*, contents: str, file_path: Path) -> tuple[SourceEntry, ...]:
    """Load and parse sources YAML contents as source discovery does."""

    return _native.parse_sources_document(
        _native.load_yaml_document(str(file_path), contents, "source"),
        str(file_path),
    )


def parse_schema_yml(
    *, contents: str, file_path: Path
) -> tuple[tuple[SchemaModelEntry, ...], tuple[SchemaSeedEntry, ...]]:
    """Load and parse schema or seed YAML contents as schema discovery does."""

    return (), _native.parse_schema_document(
        _native.load_yaml_document(str(file_path), contents, "schema"),
        str(file_path),
    )
