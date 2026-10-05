"""Seeded projects that mix every SQL construct the model renderer handles."""

from __future__ import annotations

import random
from pathlib import Path

from scripts.cold_compile_performance.models import RandomRenderProject

_MACRO_SHARE: float = 0.4
_DECLARATION_SHARE: float = 0.3
_NOISE_SHARE: float = 0.3
_FINANCE_OWNER_DIRECTORY: str = "marts"
_DIRECTORIES: tuple[str, ...] = (
    "staging",
    "marts",
    "marts/finance",
    "reporting/daily",
    "reporting/weekly",
)
_MACROS: str = """def cents(column: str) -> str:
    return f"CAST({column} * 100 AS BIGINT)"


def quantity_floor(ctx) -> str:
    return str(ctx.constants["minimum_quantity"])


def constant_names(ctx) -> str:
    return "'" + ",".join(sorted(ctx.constants)) + "'"


def label(text: str, suffix: str = "item") -> str:
    return "'" + text + "_" + suffix + "'"


def wrap(sql: str) -> str:
    return "(" + sql + ")"


def status_value(ctx) -> str:
    return ctx.render_enum_member(enum_name="order_status", member_name="ACTIVE")


def relation(table) -> str:
    return f"SELECT order_id FROM {table}"


def first_order() -> str:
    return '(SELECT min(order_id) FROM __ref("orders_000"))'


def lookup_note(ctx) -> str:
    try:
        return str(ctx.constants["absent_constant"])
    except KeyError as error:
        return "'" + str(error).replace("'", "") + "'"
"""
_FINANCE_MACROS: str = """def finance_floor(ctx) -> str:
    return ctx.render_constant("finance_floor")
"""
_ENUMS: str = (
    'ENUM (\n  name order_status,\n  members (\n    ACTIVE "active",\n'
    '    CLOSED "closed\'s",\n  ),\n);\n'
)
_CONSTANTS: str = (
    "CONSTANT (name minimum_quantity, value 2);\n"
    'CONSTANT (name regions, value ["north", "south"]);\n'
    'CONSTANT (name label_text, value "it\'s");\n'
)
_MACRO_FRAGMENTS: tuple[str, ...] = (
    "@cents('base.amount')",
    "@cents( 'base.amount' )",
    "@quantity_floor()",
    "@constant_names()",
    "@label('order', suffix='line')",
    "@wrap(@cents('base.amount'))",
    "@status_value()",
    "@lookup_note()",
)
_DECLARATION_FRAGMENTS: tuple[str, ...] = (
    '@enum("order_status").ACTIVE',
    "@enum('order_status') . CLOSED",
    '@enum(\n  "order_status"\n).ACTIVE',
    '@const("minimum_quantity")',
    '@const ( "regions" )',
    "@const('label_text')",
)
_NOISE_FRAGMENTS: tuple[str, ...] = (
    "'@enum(\"order_status\").ACTIVE stays quoted'",
    '$$ @const("regions") stays dollar quoted $$',
    "'café ☕'",
    "'@@region'",
    "'it''s'",
)
_DIALECT_NOISE: dict[str, tuple[str, ...]] = {
    "duckdb": ("E'tab\\tstop'", "'/* not a comment */'"),
    "snowflake": ("'path\\\\to'", "'// not a comment'"),
}
_DIALECT_COMMENTS: dict[str, str] = {
    "duckdb": '/* note: @enum("order_status").CLOSED __ref("orders_missing") */',
    "snowflake": '// note: @enum("order_status").CLOSED __ref("orders_missing")',
}
_ERROR_FRAGMENTS: tuple[str, ...] = (
    '@enum("order_status").MISSING',
    "@missing_macro()",
    "@cents(amount)",
    "@enum(order_status).ACTIVE",
    '@const("absent_constant")',
    "@finance_floor()",
    '(SELECT 1 FROM __ref("orders_absent"))',
    '/* unclosed @const("regions")',
)


def write_random_render_project(*, project_dir: Path, project: RandomRenderProject) -> None:
    """Write a seeded project whose models mix every construct the renderer handles."""

    rng: random.Random = random.Random(project.seed)
    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            f'name = "orders"\nadapter = "{project.adapter}"\n'
            '[defaults]\ndatabase = "warehouse"\nschema = "analytics"\n'
            '[vars]\nregion = "north"\nminimum_total = "10"\n'
            "[scopes]\nenforce_placement = false\n"
        ),
        "constants/policy.sql": _CONSTANTS,
        "enums/order_status.sql": _ENUMS,
        "macros/formatting.py": _MACROS,
        "models/marts/_sqlbuild/_constants/finance.sql": (
            "CONSTANT (name finance_floor, value 5);\n"
        ),
        "models/marts/_sqlbuild/_macros/finance.py": _FINANCE_MACROS,
    }
    error_models: frozenset[int] = frozenset(
        rng.sample(range(1, project.model_count), project.errors) if project.errors else ()
    )
    for index in range(project.model_count):
        directory: str = "staging" if index == 0 else rng.choice(_DIRECTORIES)
        files[f"models/{directory}/orders_{index:03d}.sql"] = _render_model_sql(
            rng=rng,
            index=index,
            directory=directory,
            project=project,
            error=index in error_models,
        )
    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")


def _render_model_sql(
    *, rng: random.Random, index: int, directory: str, project: RandomRenderProject, error: bool
) -> str:
    columns: list[str] = ["base.order_id AS order_id", "base.amount AS amount"]
    fragments: list[str] = []
    if rng.random() < _MACRO_SHARE:
        fragments.extend(rng.sample(_MACRO_FRAGMENTS, rng.randint(1, 3)))
    if directory == _FINANCE_OWNER_DIRECTORY and rng.random() < _MACRO_SHARE:
        fragments.append("@finance_floor()")
    if rng.random() < _DECLARATION_SHARE:
        fragments.extend(rng.sample(_DECLARATION_FRAGMENTS, rng.randint(1, 3)))
    if rng.random() < _NOISE_SHARE:
        fragments.append(rng.choice(_NOISE_FRAGMENTS + _DIALECT_NOISE[project.adapter]))
    if project.generated_references and rng.random() < _NOISE_SHARE:
        fragments.append(rng.choice(("@first_order()", "@wrap(@first_order())")))
    if error:
        fragments.append(rng.choice(_ERROR_FRAGMENTS))
    columns.extend(f"{fragment} AS value_{position}" for position, fragment in enumerate(fragments))
    source: str = (
        "(SELECT 1 AS order_id, 12.5 AS amount)"
        if index == 0
        else f'__ref("orders_{rng.randrange(index):03d}")'
    )
    comments: tuple[str, ...] = tuple(
        comment
        for comment in (
            '-- authored @enum("order_status").ACTIVE',
            _DIALECT_COMMENTS[project.adapter],
        )
        if rng.random() < _NOISE_SHARE
    )
    select_list: str = ",\n  ".join(columns)
    return (
        f'MODEL (description "Test model orders_{index:03d}.", materialized view);\n'
        + "".join(f"{comment}\n" for comment in comments)
        + f"SELECT\n  {select_list}\nFROM {source} AS base\n"
    )
