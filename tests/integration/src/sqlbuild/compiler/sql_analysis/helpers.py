"""Read the wheel-site records a test process wrote."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from sqlbuild.compiler.references.main.extract_relation_names import extract_relation_names
from sqlbuild.compiler.references.models import RelationName
from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_SITE_RECORD_PREFIX
from tests.integration.src.sqlbuild.compiler.compile.helpers import ExpansionFailureCapture


def recorded_rows(root: Path) -> tuple[tuple[str, str, int], ...]:
    """Return every `(site, api, calls)` row the site recorder wrote below `root`."""

    rows: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob(f"{POLYGLOT_SITE_RECORD_PREFIX}*.json")):
        for site, api, count in json.loads(path.read_text(encoding="utf-8"))["calls"]:
            rows.append((str(site), str(api), int(count)))
    return tuple(rows)


def relation_names_outcome(sql: str, dialect: str | None) -> object:
    """The extracted `(relations, sorted temporary names)`, None if unparseable, or the error."""

    capture: ExpansionFailureCapture = ExpansionFailureCapture()
    extracted: list[tuple[tuple[RelationName, ...], frozenset[str]] | None] = [None]
    with capture:
        extracted[0] = extract_relation_names(sql=sql, dialect=dialect)
    return {
        True: lambda: _relation_view(extracted[0]),
        False: lambda: (type(capture.failure).__name__, str(capture.failure)),
    }[capture.failure is None]()


def _relation_view(
    extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None,
) -> object:
    return {
        True: lambda: None,
        False: lambda: _present_relation_view(
            cast(tuple[tuple[RelationName, ...], frozenset[str]], extracted)
        ),
    }[extracted is None]()


def _present_relation_view(
    extracted: tuple[tuple[RelationName, ...], frozenset[str]],
) -> tuple[tuple[tuple[str, str | None, str | None], ...], tuple[str, ...]]:
    relations, temporary = extracted
    return (
        tuple((relation.name, relation.schema, relation.database) for relation in relations),
        tuple(sorted(temporary)),
    )
