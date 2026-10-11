"""Relation references in the SQL-test helper CTEs a test reads, and what cannot resolve."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile._helpers.refs.references import (
    reference_call_location,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
from sqlbuild.spec.contracts.models import SourceLocation


def sql_test_cte_location(
    *,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    cte_name: str,
    call: str | None,
) -> SourceLocation:
    """Locate a call inside one CTE of a SQL test block, else the CTE header, else the block."""

    contents: str = test_file.contents
    block_offset: int = max(contents.find(test_block.sql_body), 0)
    header: re.Match[str] | None = re.compile(
        rf"(?<![\w$]){re.escape(cte_name)}[\"`]?\s+AS\s*\(", re.IGNORECASE
    ).search(contents, block_offset)
    start: int = header.start() if header is not None else block_offset
    text: str = cte_name if header is not None else ""
    if call is not None and header is not None:
        found: re.Match[str] | None = re.compile(re.escape(call), re.IGNORECASE).search(
            contents, header.end()
        )
        if found is not None:
            start, text = found.start(), call
    return reference_call_location(
        path=test_file.relative_path, text=contents, start=start, call=text
    )
