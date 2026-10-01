"""Project writers shared by lint behavior tests."""

import itertools
from pathlib import Path

_PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n'


def write_fixture_format_project(
    *, tmp_path: Path, fixture_sql: str, project_toml: str = _PROJECT_TOML
) -> Path:
    """Write a contracted two-model project with one SQL fixture."""

    (tmp_path / "sqlbuild_project.toml").write_text(project_toml, encoding="utf-8")
    staging_model: Path = tmp_path / "models" / "stg_rows.sql"
    staging_model.parent.mkdir()
    staging_model.write_text(
        "MODEL (\n"
        '  description "Staged rows",\n'
        "  contract enforced,\n"
        "  columns (\n"
        "    id (type INTEGER, nullable false),\n"
        "    flag (type BOOLEAN, nullable true),\n"
        "  ),\n"
        ");\n\n"
        "SELECT 1 AS id, TRUE AS flag\n",
        encoding="utf-8",
    )
    (tmp_path / "models" / "rows.sql").write_text(
        'MODEL (description "Rows");\n\nSELECT id, flag FROM __ref("stg_rows")\n',
        encoding="utf-8",
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_rows.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "TEST();\n\n"
        "WITH\n"
        f"__ref__stg_rows AS ({fixture_sql}),\n"
        "__expected__rows AS (SELECT 1 AS id, TRUE AS flag)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )
    return test_file


_KEYWORD_NAMED_IDENTIFIERS: tuple[str, ...] = (
    "Left",
    "Filter",
    "Rows",
    "Index",
    "View",
    "Replace",
    "Any",
    "Some",
    "Only",
    "Semi",
    "Anti",
    "Pivot",
    "Tablesample",
    "Range",
    "Row",
    "Nulls",
    "Ignore",
    "Within",
    "Recursive",
    "Exclude",
)
_SHAPES: tuple[tuple[str, str, int], ...] = (
    ("projection", "select {name} from orders", 1),
    ("alias", "select order_id as {name} from orders", 1),
    ("qualified column", "select o.{name} from orders o", 1),
    ("qualified table", "select * from inventory.{name}", 1),
    ("table and qualifier", "select {name}.order_id from {name}", 2),
)


def keyword_name_positions() -> tuple[tuple[str, str, str, str, int], ...]:
    """Return every (dialect, name, position, query template, occurrences) combination."""

    return tuple(
        (dialect, name, *shape)
        for dialect, name, shape in itertools.product(
            ("duckdb", "bigquery"), _KEYWORD_NAMED_IDENTIFIERS, _SHAPES
        )
    )
