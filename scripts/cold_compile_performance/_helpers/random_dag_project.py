"""Seeded DuckDB projects whose models bind against shapes inferred from their producers."""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path

from scripts.cold_compile_performance.models import RandomDagProject

_RANDOM_DAG_ROOTS: int = 3
_RANDOM_DAG_ROOT_SHARE: float = 0.1
_RANDOM_DAG_FEATURE_SHARE: float = 0.1
_RANDOM_DAG_WINDOW: int = 12
_RANDOM_DAG_SOURCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("raw_orders", ("id", "quantity", "status")),
    ("raw_customers", ("id", "region")),
)


def write_random_dag_project(*, project_dir: Path, project: RandomDagProject) -> tuple[str, ...]:
    """Write seeded models over inferred shapes; return model names in topological order."""

    rng: random.Random = random.Random(project.seed)
    project_dir.mkdir(parents=True, exist_ok=True)
    rules: str = ", ".join(f'"{code}"' for code in project.rules)
    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = [{rules}]\n', encoding="utf-8"
    )
    (project_dir / "sources").mkdir(exist_ok=True)
    (project_dir / "sources" / "raw.yml").write_text(
        "sources:\n"
        "  - name: raw_orders\n    description: Test source raw_orders.\n"
        "    expression: SELECT 1 AS id, 2 AS quantity, 'open' AS status\n"
        "  - name: raw_customers\n    description: Test source raw_customers.\n"
        "    expression: SELECT 1 AS id, 'north' AS region\n",
        encoding="utf-8",
    )
    models: Path = project_dir / "models"
    models.mkdir(exist_ok=True)
    columns: dict[str, tuple[str, ...]] = {}
    names: list[str] = []
    for index in range(project.model_count):
        name: str = f"orders_{index:03d}"
        options: str = ""
        body: str
        output: tuple[str, ...]
        if index < _RANDOM_DAG_ROOTS or rng.random() < _RANDOM_DAG_ROOT_SHARE:
            source, output = rng.choice(_RANDOM_DAG_SOURCES)
            body = f'SELECT * FROM __source("{source}")'
        else:
            body, output = _random_dag_query(
                rng=rng, index=index, names=names, columns=columns, errors=project.errors
            )
        if project.run_ids and rng.random() < _RANDOM_DAG_FEATURE_SHARE:
            options += ', tags ["${CTX:run.id}"]'
        if project.analysis_opt_outs and rng.random() < _RANDOM_DAG_FEATURE_SHARE:
            options += ", sql_analysis false"
        (models / f"{name}.sql").write_text(
            f'MODEL (description "Test model {name}.", materialized view{options});\n{body}\n',
            encoding="utf-8",
        )
        columns[name] = output
        names.append(name)
    if project.missing_reference:
        (models / "orders_missing.sql").write_text(
            'MODEL (description "Test model orders_missing.", materialized view);\n'
            'SELECT id FROM __ref("orders_absent")\n',
            encoding="utf-8",
        )
    if project.cycle:
        for name, upstream in (
            ("orders_loop_a", "orders_loop_b"),
            ("orders_loop_b", "orders_loop_a"),
        ):
            (models / f"{name}.sql").write_text(
                f'MODEL (description "Test model {name}.", materialized view);\n'
                f'SELECT id FROM __ref("{upstream}")\n',
                encoding="utf-8",
            )
    return tuple(names)


def _random_dag_query(
    *,
    rng: random.Random,
    index: int,
    names: list[str],
    columns: dict[str, tuple[str, ...]],
    errors: bool,
) -> tuple[str, tuple[str, ...]]:
    upstream: str = rng.choice(names[max(0, index - _RANDOM_DAG_WINDOW) :])
    other: str = rng.choice(names)
    if errors and rng.random() < _RANDOM_DAG_FEATURE_SHARE:
        return (
            f'SELECT id, missing_{index} FROM __ref("{upstream}")',
            ("id", f"missing_{index}"),
        )
    return rng.choice(_query_builders())(
        index=index, upstream=upstream, other=other, columns=columns
    )


def _star_query(
    *, index: int, upstream: str, other: str, columns: dict[str, tuple[str, ...]]
) -> tuple[str, tuple[str, ...]]:
    del index, other
    return f'SELECT * FROM __ref("{upstream}")', columns[upstream]


def _projection_query(
    *, index: int, upstream: str, other: str, columns: dict[str, tuple[str, ...]]
) -> tuple[str, tuple[str, ...]]:
    del other
    return (
        f"SELECT id, {columns[upstream][-1]} AS kept_{index}, "
        f'CAST(id AS BIGINT) * {index} AS value_{index} FROM __ref("{upstream}")',
        ("id", f"kept_{index}", f"value_{index}"),
    )


def _join_query(
    *, index: int, upstream: str, other: str, columns: dict[str, tuple[str, ...]]
) -> tuple[str, tuple[str, ...]]:
    return (
        f"SELECT a.*, b.{columns[other][-1]} AS joined_{index} "
        f'FROM __ref("{upstream}") AS a LEFT JOIN __ref("{other}") AS b ON a.id = b.id',
        (*columns[upstream], f"joined_{index}"),
    )


def _union_query(
    *, index: int, upstream: str, other: str, columns: dict[str, tuple[str, ...]]
) -> tuple[str, tuple[str, ...]]:
    del index, columns
    return (
        f'SELECT id FROM __ref("{upstream}") UNION ALL SELECT id FROM __ref("{other}")',
        ("id",),
    )


def _aggregate_query(
    *, index: int, upstream: str, other: str, columns: dict[str, tuple[str, ...]]
) -> tuple[str, tuple[str, ...]]:
    del other, columns
    return (
        f'SELECT id, COUNT(*) AS row_count_{index} FROM __ref("{upstream}") GROUP BY id',
        ("id", f"row_count_{index}"),
    )


def _query_builders() -> tuple[Callable[..., tuple[str, tuple[str, ...]]], ...]:
    return (_star_query, _projection_query, _join_query, _union_query, _aggregate_query)
