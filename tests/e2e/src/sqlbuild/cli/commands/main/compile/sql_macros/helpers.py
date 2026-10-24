"""A small DuckDB orders project and the SQL macros its E2E tests call."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_SEED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("order_id", "BIGINT"),
    ("status", "VARCHAR"),
    ("amount_cents", "BIGINT"),
    ("fee_cents", "BIGINT"),
    ("tax_cents", "BIGINT"),
    ("created_at", "TIMESTAMP"),
    ("updated_at", "TIMESTAMP"),
    ("is_deleted", "BOOLEAN"),
    ("country_code", "VARCHAR"),
)

BASE_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "shop"\nadapter = "duckdb"\n\n[connection]\ndatabase = "shop.duckdb"\n\n'
        "[scopes]\nenforce_placement = false\n"
    ),
    "seeds/raw_orders.csv": (
        "order_id,status,amount_cents,fee_cents,tax_cents,created_at,updated_at,is_deleted,"
        "country_code\n"
        "1,open,1250,100,20,2026-01-01 00:00:00,2026-01-02 00:00:00,false,GB\n"
        "1,open,1300,100,20,2026-01-01 00:00:00,2026-01-03 00:00:00,false,GB\n"
        "2,closed,500,50,5,2026-01-01 00:00:00,2026-01-01 00:00:00,false,FR\n"
        "3,open,900,0,0,2026-01-01 00:00:00,2026-01-04 00:00:00,true,US\n"
    ),
    "seeds/raw_orders.yml": "seeds:\n  - name: raw_orders\n    description: Raw orders.\n"
    "    columns:\n"
    + "".join(
        f"      - name: {name}\n        type: {data_type}\n" for name, data_type in _SEED_COLUMNS
    ),
    "enums/order_status.sql": 'ENUM (name order_status, members (OPEN "open", CLOSED "closed"));\n',
    "constants/supported_countries.sql": (
        'CONSTANT (name supported_countries, value ["GB", "FR", "HK"]);\n'
    ),
    "models/staging/stg_orders.sql": (
        'MODEL (description "Staged orders");\n\nSELECT * FROM __seed("raw_orders")\n'
    ),
}

CENTS_TO_DOLLARS: dict[str, str] = {
    "macros/sql/cents_to_dollars.sql": (
        'MACRO (\n  description "Cents to dollars",\n'
        "  arguments (amount_cents BIGINT, places INT CONST DEFAULT 2),\n"
        "  returns DECIMAL(18, 2),\n);\n\n"
        "CAST(ROUND(@amount_cents / 100, @places) AS DECIMAL(18, 2))\n"
    )
}
NET_AMOUNT: dict[str, str] = {
    "macros/sql/net_amount.sql": (
        'MACRO (\n  description "Net amount in dollars",\n'
        "  arguments (gross_cents BIGINT, refund_cents BIGINT),\n"
        "  returns DECIMAL(18, 2),\n);\n\n"
        "@sql.cents_to_dollars(@gross_cents - COALESCE(@refund_cents, 0))\n"
    )
}
CLEAN_ORDERS: dict[str, str] = {
    "macros/sql/clean_orders.sql": (
        'MACRO (\n  description "Deduplicated, non-deleted orders",\n'
        "  arguments (src RELATION (order_id BIGINT, updated_at TIMESTAMP, is_deleted BOOLEAN)),\n"
        ");\n\n"
        "WITH live AS (SELECT * FROM @src WHERE NOT is_deleted),\n"
        "ranked AS (\n"
        "  SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC) AS "
        "row_num\n"
        "  FROM live\n),\n"
        "latest AS (SELECT * EXCLUDE (row_num) FROM ranked WHERE row_num = 1)\n"
    )
}
AUDIT_COLUMNS: dict[str, str] = {
    "macros/sql/audit_columns.sql": (
        'MACRO (\n  description "Standard audit columns",\n'
        "  arguments (src RELATION (created_at TIMESTAMP, updated_at TIMESTAMP)),\n);\n\n"
        "SELECT @src.created_at, @src.updated_at, @src.updated_at > @src.created_at AS "
        "was_updated\n"
    )
}
IS_OPEN_STATUS: dict[str, str] = {
    "macros/sql/is_open_status.sql": (
        'MACRO (\n  description "Whether a status is still open",\n'
        "  arguments (status VARCHAR, closed ENUM order_status DEFAULT "
        '@enum("order_status").CLOSED),\n'
        "  returns BOOLEAN,\n);\n\n@status <> @closed\n"
    )
}
IN_SUPPORTED_COUNTRY: dict[str, str] = {
    "macros/sql/in_supported_country.sql": (
        'MACRO (\n  description "Whether a country code is supported",\n'
        '  arguments (country VARCHAR, countries LIST VARCHAR DEFAULT ["GB", "FR"]),\n'
        "  returns BOOLEAN,\n);\n\n@country IN @countries\n"
    )
}
LATEST_PER_KEY: dict[str, str] = {
    "macros/sql/latest_per_key.sql": (
        'MACRO (\n  description "Latest row per key",\n'
        "  arguments (\n    src RELATION (updated_at TIMESTAMP),\n    key COLUMN OF src,\n  "
        "),\n);\n\n"
        "WITH latest_ranked AS (\n"
        "  SELECT @src.*, ROW_NUMBER() OVER (PARTITION BY @key ORDER BY updated_at DESC) AS "
        "row_num\n"
        "  FROM @src\n),\n"
        "latest_rows AS (SELECT * EXCLUDE (row_num) FROM latest_ranked WHERE row_num = 1)\n"
    )
}
BRACKET: dict[str, str] = {
    "macros/python/labels.py": (
        "def bracket(expression: str) -> str:\n"
        '    """Wrap an expression in brackets."""\n'
        "    return f\"'[' || CAST({expression} AS VARCHAR) || ']'\"\n"
    )
}
ALL_MACROS: dict[str, str] = {
    **CENTS_TO_DOLLARS,
    **NET_AMOUNT,
    **CLEAN_ORDERS,
    **AUDIT_COLUMNS,
    **IS_OPEN_STATUS,
    **IN_SUPPORTED_COUNTRY,
    **LATEST_PER_KEY,
    **BRACKET,
}
MODEL_HEADER: str = 'MODEL (description "Orders");\n\n'
DATABASE: str = "shop.duckdb"


def orders_model(sql: str) -> dict[str, str]:
    """The `orders` mart model with `sql` as its query."""

    return {"models/marts/orders.sql": MODEL_HEADER + sql}


def run_project(
    *, tmp_path: Path, files: Mapping[str, str], command: tuple[str, ...]
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    """Write the base project with `files` over it and run one sqb command against it."""

    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="shop", repo_files={**BASE_FILES, **files}
    )
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", *command), project_dir=project_dir
    )
    return project_dir, result


def output(result: subprocess.CompletedProcess[str]) -> str:
    """Everything one command printed."""

    return result.stdout + result.stderr


def inspected_text(*, project_dir: Path, relative_paths: tuple[str, ...]) -> str:
    """The text of every project file a test inspects."""

    return "".join(
        (project_dir / relative_path).read_text(encoding="utf-8")
        for relative_path in relative_paths
    )


WRAPPING_MACROS: dict[str, str] = {
    "macros/python/wrapping.py": (
        "def wrap(expr: str) -> str:\n"
        '    """Wrap an expression in parentheses."""\n'
        '    return f"({expr})"\n\n\n'
        "def pick(mapping: dict) -> str:\n"
        '    """The expression under key a."""\n'
        '    return mapping["a"]\n\n\n'
        "def first(items: list) -> str:\n"
        '    """The first expression of a list."""\n'
        "    return items[0]\n\n\n"
        "def noted(expr: str) -> str:\n"
        '    """An expression and a block comment."""\n'
        '    return f"UPPER({expr}) /* noted */"\n'
    )
}
CHECK_MACRO_PATH: str = "macros/sql/check.sql"


def with_rules(*codes: str) -> dict[str, str]:
    """The base project with the given Rules selected."""

    selected: str = ", ".join(f'"{code}"' for code in codes)
    return {
        "sqlbuild_project.toml": BASE_FILES["sqlbuild_project.toml"]
        + f"\n[rules]\nselect = [{selected}]\n"
    }


def check_macro(arguments: str, body: str) -> dict[str, str]:
    """The SQL macro `check` returning a boolean from `body`."""

    return {
        CHECK_MACRO_PATH: (
            f'MACRO (\n  description "A check",\n  arguments ({arguments}),\n'
            f"  returns BOOLEAN,\n);\n\n{body}\n"
        )
    }


def python_normalise_macros(names: list[str]) -> dict[str, str]:
    """One Python macro file per name in the `normalise` bucket of `macros/python/`."""

    return {
        f"macros/python/normalise/{name}.py": (
            f"def {name}(expression: str) -> str:\n"
            f'    """Clean a value with {name}."""\n'
            '    return f"TRIM({expression})"\n'
        )
        for name in names
    }


def sql_text_macros(folder: str, names: list[str]) -> dict[str, str]:
    """One lower-casing SQL macro file per name in `macros/sql/<folder>/`."""

    return {
        f"macros/sql/{folder}/{name}.sql": (
            f'MACRO (description "Tidy {name}", arguments (value VARCHAR), returns VARCHAR);\n\n'
            "LOWER(@value)\n"
        )
        for name in names
    }


def text_macro(name: str, returns: str, body: str, argument: str = "VARCHAR") -> dict[str, str]:
    """The SQL macro `name` taking one `argument`-typed value and declaring `returns`."""

    return _value_macro(name, f"  returns {returns},\n", body, argument)


def untyped_text_macro(name: str, body: str, argument: str = "VARCHAR") -> dict[str, str]:
    """The SQL macro `name` taking one `argument`-typed value without declaring `returns`."""

    return _value_macro(name, "", body, argument)


def _value_macro(name: str, declared: str, body: str, argument: str) -> dict[str, str]:
    """The SQL macro `name` taking one `argument`-typed value, with its `declared` header lines."""

    return {
        f"macros/sql/{name}.sql": (
            f'MACRO (\n  description "Text from a value",\n  arguments (value {argument}),\n'
            f"{declared});\n\n{body}\n"
        )
    }


def contract_model(name: str, columns: str, sql: str) -> dict[str, str]:
    """The mart model `name` with an enforced contract over `columns`."""

    return {
        f"models/marts/{name}.sql": (
            f'MODEL (\n  description "Typed {name}",\n  contract enforced,\n'
            f"  columns ({columns}),\n);\n\n{sql}"
        )
    }


def typed_position_files(shape: str, sql: str, declared: str) -> dict[str, str]:
    """The `orders` model over `sql`, contracted itself, contracted downstream, or uncontracted."""

    downstream: dict[str, str] = contract_model(
        "order_x", f"x (type {declared})", 'SELECT b.x FROM __ref("orders") AS b\n'
    )
    shapes: dict[str, dict[str, str]] = {
        "contracted": contract_model("orders", f"x (type {declared})", sql),
        "downstream": {**orders_model(sql), **downstream},
        "uncontracted": orders_model(sql),
    }
    return shapes[shape]


def lineage_edges(printed: str) -> list[str]:
    """The `source -> target` edges a list-format lineage command printed."""

    return [edge.strip() for edge in re.findall(r"^.*->.*$", printed, flags=re.MULTILINE)]


def adapter_project(adapter: str) -> dict[str, str]:
    """The orders project configured for `adapter`, compiled without a warehouse."""

    return {
        "sqlbuild_project.toml": (
            f'name = "shop"\nadapter = "{adapter}"\ndefault_target = "dev"\n\n'
            '[targets.dev]\ndatabase = "warehouse"\nschema = "analytics"\n\n'
            "[scopes]\nenforce_placement = false\n"
        )
    }


def picked_orders(body: str) -> dict[str, str]:
    """The CTE-list macro `pick` over relation `src` with `body`, called once as `__cte := a`."""

    return {
        "macros/sql/pick.sql": (
            'MACRO (\n  description "Picked orders",\n'
            "  arguments (src RELATION (order_id BIGINT)),\n);\n\n" + body + "\n"
        ),
        **orders_model(
            'WITH raw AS (SELECT * FROM __ref("stg_orders")),\n'
            "@sql.pick(raw, __cte := a)\nSELECT * FROM a\n"
        ),
    }
