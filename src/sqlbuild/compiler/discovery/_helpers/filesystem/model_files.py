"""Assembly of one discovered SQL model file from its pre-matched MODEL header."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.declarations import (
    parse_model_constant_declarations,
    parse_model_enum_declarations,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    matched_model_header_column_locations,
    matched_model_output_column_locations,
    parse_matched_model_sql,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile, ModelHeaderMatch


def discover_matched_model_file(
    *,
    file_path: Path,
    relative_path: Path,
    contents: str,
    header_match: ModelHeaderMatch | None,
    extract_implicit_alias_columns: bool,
    extract_output_column_locations: bool,
) -> DiscoveredSqlModelFile:
    """Build one model file from contents whose MODEL header was matched exactly once."""

    header_values, query_sql = parse_matched_model_sql(
        header_match=header_match, file_path=file_path
    )
    return DiscoveredSqlModelFile(
        file_path=file_path,
        relative_path=relative_path,
        contents=contents,
        header_values=header_values,
        header_column_locations=matched_model_header_column_locations(
            contents=contents, header_match=header_match, relative_path=relative_path
        ),
        output_column_locations=(
            matched_model_output_column_locations(
                contents=contents,
                header_match=header_match,
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
        extract_implicit_alias_columns=extract_implicit_alias_columns,
    )
