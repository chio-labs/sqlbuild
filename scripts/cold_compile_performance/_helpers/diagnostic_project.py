"""Synthetic workloads for error-only compile paths and deep poisoned lineage."""

from pathlib import Path


def write_diagnostic_project(
    *, project_dir: Path, model_count: int = 3, width: int = 32, depth: int = 100
) -> None:
    """Generate large macro-backed CTE models with independent errors and warnings."""
    project_dir.mkdir(parents=True, exist_ok=True)
    models: Path = project_dir / "models"
    models.mkdir(exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "diagnostic_orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    columns: list[str] = [f"amount_{index:03}" for index in range(width)]
    declarations: str = ", ".join(f"{column} (type INTEGER)" for column in columns)
    (models / "orders.sql").write_text(
        f"MODEL (materialized view, contract enforced, columns ({declarations}));\nSELECT "
        + ", ".join(f"CAST(1 AS INTEGER) AS {column}" for column in columns)
    )
    for model_index in range(model_count):
        ctes: list[str] = ['input_orders AS (SELECT * FROM __ref("orders"))']
        previous: str = "input_orders"
        for level in range(depth):
            name: str = f"stage_{level:03}"
            projection: str = ",\n".join(f"  {column} + 1 AS {column}" for column in columns)
            ctes.append(f"{name} AS (\nSELECT\n{projection}\nFROM {previous}\n)")
            previous = name
        errors: list[str] = [f"missing_{index:03} AS broken_{index:03}" for index in range(50)]
        warnings: list[str] = [
            f"CAST(TIMESTAMP '2026-04-01' AS INTEGER) AS risky_{index:03}" for index in range(50)
        ]
        sql: str = "MODEL (materialized view);\nWITH\n" + ",\n".join(ctes)
        sql += "\nSELECT\n" + ",\n".join((*errors, *warnings)) + f"\nFROM {previous}\n"
        name = f"large_orders_{model_index}"
        (models / f"{name}.sql").write_text(sql)
        (models / f"downstream_orders_{model_index}.sql").write_text(
            "MODEL (materialized view);\nSELECT "
            + ", ".join(f"broken_{index:03} + 1 AS result_{index:03}" for index in range(50))
            + f' FROM __ref("{name}")'
        )


def write_cascade_project(*, project_dir: Path, depth: int, width: int = 50) -> None:
    """Generate a reverse-named DAG with many independently poisoned output columns."""
    project_dir.mkdir(parents=True, exist_ok=True)
    models: Path = project_dir / "models"
    models.mkdir(exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "cascade_orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    columns: list[str] = [f"amount_{index:03}" for index in range(width)]
    declarations: str = ", ".join(f"{column} (type INTEGER)" for column in columns)
    header: str = f"MODEL (materialized view, contract enforced, columns ({declarations}));\n"
    (models / "input_orders.sql").write_text(
        f"MODEL (materialized view, contract enforced, columns ({declarations}, "
        "ordered_at (type TIMESTAMP)));\nSELECT "
        + ", ".join(f"CAST(1 AS INTEGER) AS {column}" for column in columns)
        + ", CAST('2026-04-01' AS TIMESTAMP) AS ordered_at"
    )
    root: str = ", ".join(f"{column} + ordered_at AS {column}" for column in columns)
    previous: str = f"orders_{depth:03}"
    (models / f"{previous}.sql").write_text(
        header + "SELECT " + root + ' FROM __ref("input_orders")'
    )
    for level in reversed(range(depth)):
        name: str = f"orders_{level:03}"
        (models / f"{name}.sql").write_text(
            header
            + "SELECT "
            + ", ".join(f"{column} > TIMESTAMP '2026-04-01' AS {column}" for column in columns)
            + f' FROM __ref("{previous}")'
        )
        previous = name
