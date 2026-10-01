"""Project writers shared by lint behavior tests."""

import itertools
import re
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


_RESERVED_KEYWORDS_DIR: Path = (
    Path(__file__).resolve().parents[5]
    / "crates"
    / "sqlbuild-rules-native"
    / "src"
    / "sql_tokens"
    / "reserved_keywords"
)
_DIALECTS: tuple[str, ...] = ("duckdb", "postgres", "bigquery", "snowflake", "tsql", "databricks")
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
    "Preceding",
    "Key",
    "Type",
    "Date",
    "First",
    "Value",
    "Order",
    "Union",
)
_NAME_SHAPES: tuple[tuple[str, str], ...] = (
    ("alias", "select order_id as {name} from orders"),
    ("qualified column", "select o.{name} from orders o"),
    ("qualified table", "select * from inventory.{name}"),
)
_NON_RESERVED_SHAPES: tuple[tuple[str, str], ...] = (
    ("projection", "select {name} from orders"),
    ("table", "select * from {name}"),
    ("operand", "select order_id, {name} ^ 2 from orders"),
)
_DUCKDB_SHAPES: tuple[tuple[str, str], ...] = (("struct key", "select {{{name}: 1}} as s"),)


def reserved_keywords(dialect: str) -> frozenset[str]:
    """Return the lower-case reserved keywords of one dialect from the native data files."""

    text: str = (_RESERVED_KEYWORDS_DIR / f"{dialect}.txt").read_text(encoding="utf-8")
    return frozenset(re.findall(r"^[a-z_]+$", text, flags=re.MULTILINE))


def keyword_name_positions() -> tuple[tuple[str, str, str, str], ...]:
    """Return (dialect, name, position, template) for names that must keep their case."""

    positions: list[tuple[str, str, str, str]] = []
    for dialect, name in itertools.product(_DIALECTS, _KEYWORD_NAMED_IDENTIFIERS):
        unreserved_shapes: tuple[tuple[str, str], ...] = _NON_RESERVED_SHAPES + {
            "duckdb": _DUCKDB_SHAPES
        }.get(dialect, ())
        shapes: tuple[tuple[str, str], ...] = (
            _NAME_SHAPES
            + {
                False: unreserved_shapes,
                True: (),
            }[name.lower() in reserved_keywords(dialect)]
        )
        positions.extend((dialect, name, shape, template) for shape, template in shapes)
    return tuple(positions)


def reserved_keyword_pairs() -> tuple[tuple[str, str], ...]:
    """Return every (dialect, reserved keyword) pair from the native data files."""

    pairs: list[tuple[str, str]] = []
    for dialect in _DIALECTS:
        pairs.extend((dialect, keyword) for keyword in sorted(reserved_keywords(dialect)))
    return tuple(pairs)
