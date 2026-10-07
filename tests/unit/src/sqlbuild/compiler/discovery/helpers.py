from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.model_files import discover_native_model_files
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_locations,
    native_payload_error,
    native_text_runtime,
)
from sqlbuild.compiler.discovery._helpers.native.sql_test_files import (
    parse_native_sql_test_contents,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import project_native_header_values
from sqlbuild.compiler.discovery._helpers.sql.scenarios import build_sql_scenario_file
from sqlbuild.compiler.discovery._helpers.yml.schema import parse_loaded_schema_yml
from sqlbuild.compiler.discovery._helpers.yml.sources import parse_loaded_sources_yml
from sqlbuild.compiler.discovery.constants import (
    REMOVED_SQL_MODEL_HEADER_KEYS,
    SQL_MODEL_HEADER_KEYS,
    SQL_SCENARIO_HEADER_KEYS,
    SQL_TEST_HEADER_KEYS,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
)
from sqlbuild.compiler.discovery.types import NativeLocation
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


def discover_model_files(*, project_dir: Path) -> tuple[DiscoveredSqlModelFile, ...]:
    """Discover every model file with the column extraction full compilation uses."""

    return discover_native_model_files(
        project_dir=project_dir,
        extract_implicit_alias_columns=True,
        extract_output_column_locations=True,
    )


def parse_model_sql(*, contents: str, file_path: Path) -> tuple[dict[str, object], str]:
    """Parse model contents as model discovery does, returning header values and query SQL."""

    payload: tuple[object, ...] = _parsed_model(contents=contents, file_path=file_path)
    return project_native_header_values(cast(dict[str, object], payload[2])), str(payload[5])


def model_header_column_locations(
    *, contents: str, relative_path: Path
) -> dict[str, SourceLocation]:
    """Return the authored MODEL(columns) locations model discovery records."""

    payload: tuple[object, ...] = _parsed_model(contents=contents, file_path=relative_path)
    return native_locations(
        locations=cast(list[NativeLocation], payload[3]), relative_path=relative_path
    )


def _parsed_model(*, contents: str, file_path: Path) -> tuple[object, ...]:
    payload: tuple[object, ...] = _native.parse_model_contents(
        {
            "file_path": str(file_path),
            "supported_keys": sorted(SQL_MODEL_HEADER_KEYS),
            "removed_keys": sorted(REMOVED_SQL_MODEL_HEADER_KEYS),
            "extract_implicit_alias_columns": True,
            "extract_output_column_locations": False,
            **native_text_runtime(),
        },
        contents,
    )
    _raise_payload_error(payload=payload, file_path=file_path)
    return payload


def parse_sql_test_file(*, contents: str, file_path: Path) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse SQL test contents as test discovery does."""

    return parse_native_sql_test_contents(contents=contents, file_path=file_path)


def parse_sql_scenario_file(
    *, contents: str, file_path: Path, relative_path: Path
) -> DiscoveredSqlScenarioFile:
    """Parse scenario contents as scenario discovery does."""

    payload: tuple[object, ...] = _native.parse_scenario_contents(
        {
            "file_path": str(file_path),
            "test_keys": sorted(SQL_TEST_HEADER_KEYS),
            "scenario_keys": sorted(SQL_SCENARIO_HEADER_KEYS),
            **native_text_runtime(),
        },
        contents,
    )
    _raise_payload_error(payload=payload, file_path=file_path)
    return build_sql_scenario_file(
        header_values=project_native_header_values(cast(dict[str, object], payload[2])),
        sql_body=str(payload[3]),
        contents=str(payload[1]),
        file_path=file_path,
        relative_path=relative_path,
    )


def parse_sources_yml(*, contents: str, file_path: Path) -> tuple[SourceEntry, ...]:
    """Load and parse sources YAML contents as source discovery does."""

    return parse_loaded_sources_yml(
        loaded=_loaded_yaml(contents=contents, file_path=file_path, kind="source"),
        file_path=file_path,
    )


def parse_schema_yml(
    *, contents: str, file_path: Path
) -> tuple[tuple[SchemaModelEntry, ...], tuple[SchemaSeedEntry, ...]]:
    """Load and parse schema or seed YAML contents as schema discovery does."""

    return parse_loaded_schema_yml(
        loaded=_loaded_yaml(contents=contents, file_path=file_path, kind="schema"),
        file_path=file_path,
    )


def _loaded_yaml(*, contents: str, file_path: Path, kind: str) -> object:
    payload: tuple[object, ...] = _native.load_yaml_document(str(file_path), contents, kind)
    _raise_payload_error(payload=payload, file_path=file_path)
    return payload[2]


def _raise_payload_error(*, payload: tuple[object, ...], file_path: Path) -> None:
    for error in filter(None, (native_payload_error(payload=payload, file_path=file_path),)):
        raise error
