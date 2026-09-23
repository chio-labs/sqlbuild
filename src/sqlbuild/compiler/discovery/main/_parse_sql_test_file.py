"""Public discovery entry point for parsing in-memory SQL test contents."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.sql.tests import parse_sql_test_file as _parse
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock


def parse_sql_test_file(*, contents: str, file_path: Path) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse current SQL test contents into ordered test blocks."""

    return _parse(contents=contents, file_path=file_path)
