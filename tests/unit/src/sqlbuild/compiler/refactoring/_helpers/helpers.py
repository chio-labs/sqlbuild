"""Shared builders for refactoring helper tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.refactoring._helpers.columns.column_references import (
    analyze_column,
    consumer_edits,
)
from sqlbuild.compiler.refactoring._helpers.text.header_edits import (
    add_column_entry_edit,
    column_config_edits,
    column_entry_edits,
    header_tokens,
)
from sqlbuild.compiler.refactoring._helpers.text.sql_sites import analysis_sql
from sqlbuild.compiler.refactoring._helpers.text.text_edits import text_edit
from sqlbuild.compiler.refactoring.models import (
    AnalysisSql,
    BodyContext,
    BodyEdits,
    ColumnFacts,
    ColumnQuery,
    HeaderToken,
    ProjectSqlFile,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import EditKind, SqlFileRole

DIALECT: str = "duckdb"
COLUMNS: dict[tuple[str, str], tuple[str, ...]] = {
    ("ref", "fact_orders"): ("order_id", "customer_id", "amount"),
    ("ref", "customers"): ("customer_id", "amount"),
}


def plan_consumer(*, sql: str, cascade: bool) -> BodyEdits:
    """Plan renaming fact_orders.amount to revenue in one consumer query."""

    analysis: AnalysisSql = analysis_sql(text=sql, dialect=DIALECT)
    facts: ColumnFacts = analyze_column(
        analysis=analysis,
        dialect=DIALECT,
        columns=COLUMNS,
        query=ColumnQuery(column="amount", target_tables=analysis.tables[("ref", "fact_orders")]),
    )
    return consumer_edits(
        facts=facts,
        context=BodyContext(
            path="models/consumer.sql",
            contents=sql,
            map_span=lambda start, end: (start, end),
            locate=lambda offset: offset,
            fallback_offset=0,
        ),
        old="amount",
        new="revenue",
        cascade_root=cascade,
        root_stars_pass=cascade,
    )


def migrated_column_edits(contents: str) -> tuple[TextEdit, ...]:
    """Plan the header edits that rename amount to revenue with a column migration."""

    tokens: tuple[HeaderToken, ...] = header_tokens(contents=contents) or ()
    added: tuple[TextEdit, ...] = tuple(
        filter(
            None,
            (add_column_entry_edit(contents=contents, tokens=tokens, new="revenue", old="amount"),),
        )
    )
    return (
        *column_config_edits(contents=contents, tokens=tokens, old="amount", new="revenue"),
        *(
            column_entry_edits(
                contents=contents, tokens=tokens, old="amount", new="revenue", migrate=True
            )
            or added
        ),
    )


def span_edits(*, text: str, spans: tuple[tuple[int, int, str], ...]) -> tuple[TextEdit, ...]:
    """Build column edits for (start, end, replacement) spans."""

    return tuple(
        text_edit(text=text, start=start, end=end, replacement=replacement, kind=EditKind.COLUMN)
        for start, end, replacement in spans
    )


def write_tree(*, root: Path, files: dict[str, str]) -> None:
    """Write project-relative files under a root."""

    relative: str
    contents: str
    for relative, contents in files.items():
        _ = (root / relative).write_text(contents, encoding="utf-8")


def read_tree(*, root: Path) -> dict[str, str]:
    """Read every file under a root, keyed by its relative path."""

    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.sql"))
    }


def yaml_file(contents: str) -> ProjectSqlFile:
    """Wrap YAML text as one project declaration file."""

    return ProjectSqlFile(
        relative_path="seeds/customers.yml", contents=contents, role=SqlFileRole.YAML
    )
