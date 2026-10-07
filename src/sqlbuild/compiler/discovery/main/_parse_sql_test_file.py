"""Public discovery entry point for parsing in-memory SQL test contents."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.native.sql_test_files import (
    parse_native_sql_test_contents,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock


def parse_sql_test_file(*, contents: str, file_path: Path) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse current SQL test contents into ordered test blocks."""

    return parse_native_sql_test_contents(contents=contents, file_path=file_path)
