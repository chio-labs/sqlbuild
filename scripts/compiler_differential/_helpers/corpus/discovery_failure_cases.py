"""Minimal projects that fail inside project discovery, one per diagnostic family."""

from scripts.compiler_differential.constants import (
    FAILURE_BASE_CONFIG,
    FAILURE_BASE_FILES,
    FAILURE_BASE_MART,
    FAILURE_BASE_STAGING,
    FAILURE_CONFIG_PATH,
    FAILURE_MART_PATH,
    FAILURE_SOURCES_PATH,
    FAILURE_STAGING_PATH,
    GENERATOR_BOM,
)
from scripts.compiler_differential.models import FailureCase

_TASK_MODULE: str = (
    "from sqlbuild.tasks import task\n\n\n"
    "@task\ndef export_orders(ctx):\n"
    '    """Export orders."""\n'
    "    return None\n"
)
_HOOK_MODULE: str = (
    "from sqlbuild.hooks import hook\n\n\n"
    "@hook\ndef note_refresh(ctx):\n"
    '    """Log one refresh."""\n'
    "    return None\n"
)
_MACRO_MODULE: str = "def cents(value):\n    return f'{value} * 100'\n"
_SEED_DECLARATION: str = (
    "seeds:\n  - name: order_channels\n    description: Order channels.\n"
    "    columns:\n      - name: id\n        type: INTEGER\n"
    "      - name: label\n        type: VARCHAR\n"
)


def _case(*, name: str, expected_code: str, files: dict[str, str]) -> FailureCase:
    return FailureCase(
        files={**FAILURE_BASE_FILES, **files}, name=name, expected_code=expected_code
    )


def _config(extra: str) -> dict[str, str]:
    return {FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG + extra}


def discovery_failure_cases() -> tuple[FailureCase, ...]:
    """Return the discovery-time failure cases in a stable order."""

    return (
        *_config_cases(),
        *_sql_file_cases(),
        *_layout_cases(),
        *_yaml_file_cases(),
        *_conflict_cases(),
        *_python_cases(),
    )


def _config_cases() -> tuple[FailureCase, ...]:
    return (
        _case(
            name="config-bom",
            expected_code="D001",
            files={FAILURE_CONFIG_PATH: GENERATOR_BOM + FAILURE_BASE_CONFIG},
        ),
        _case(
            name="local-config-unknown-key",
            expected_code="D001",
            files={"sqlbuild_local.toml": "[settings]\nsql_analysiss = false\n"},
        ),
        _case(
            name="target-unknown-key",
            expected_code="D001",
            files=_config('\n[targets.ci]\nschema = "ci"\nwarehouse_size = "large"\n'),
        ),
        _case(
            name="dbt-unknown-key",
            expected_code="D001",
            files=_config('\n[dbt]\nproject_dir = "dbt"\nmanifest = "dbt/manifest.json"\n'),
        ),
        _case(
            name="path-defaults-unmatched",
            expected_code="D007",
            files=_config('\n[path_defaults."reporting/finance"]\nmaterialized = "table"\n'),
        ),
    )


def _sql_file_cases() -> tuple[FailureCase, ...]:
    return (
        _case(
            name="model-bom",
            expected_code="D002",
            files={FAILURE_STAGING_PATH: GENERATOR_BOM + FAILURE_BASE_STAGING},
        ),
        _case(
            name="model-missing-header",
            expected_code="D002",
            files={FAILURE_STAGING_PATH: 'SELECT order_id\nFROM __source("raw_orders")\n'},
        ),
        _case(
            name="model-unknown-header-key",
            expected_code="D002",
            files={
                FAILURE_STAGING_PATH: FAILURE_BASE_STAGING.replace(
                    '"Staged orders",', '"Staged orders",\n  materialised table,'
                )
            },
        ),
        _case(
            name="model-reserved-name",
            expected_code="D016",
            files={"models/marts/_chain_.sql": FAILURE_BASE_MART},
        ),
        _case(
            name="test-case-missing-parameter",
            expected_code="D003",
            files={
                "tests/unit/test_order_cases.sql": (
                    'TEST (\n  name "keeps_status",\n'
                    "  parameters (\n    status_value string,\n    amount_value float,\n  ),\n"
                    '  cases (\n    placed (status_value "placed"),\n  ),\n);\n\n'
                    "WITH\n__source__raw_orders AS (\n"
                    '  SELECT 1 AS order_id, 10 AS customer_id, @param("amount_value") AS amount,'
                    ' @param("status_value") AS status\n),\n'
                    "__expected__stg_orders AS (\n  SELECT 1 AS order_id\n)\nSELECT 1\n"
                )
            },
        ),
        _case(
            name="generic-audit-header",
            expected_code="D004",
            files={
                "models/marts/_sqlbuild/_audits/generic/at_least.sql": (
                    "AUDIT (unknown_option 1);\n\nSELECT * FROM @relation WHERE @column < 0\n"
                )
            },
        ),
        _case(
            name="list-constant-mixed-types",
            expected_code="D013",
            files={
                "models/staging/_sqlbuild/_constants/statuses.sql": (
                    'CONSTANT (name kept_statuses, value ["placed", 3]);\n'
                )
            },
        ),
        _case(
            name="enum-duplicate-member",
            expected_code="D013",
            files={
                "models/staging/_sqlbuild/_enums/order_status.sql": (
                    "ENUM (\n  name order_status,\n  members [PLACED, PLACED],\n);\n"
                )
            },
        ),
        _case(
            name="sql-hook-unknown-key",
            expected_code="D014",
            files={
                "hooks/sql/record_refresh.sql": (
                    'HOOK (\n  description "Record a refresh",\n  phase post,\n);\n\nSELECT 1\n'
                )
            },
        ),
        _case(
            name="sql-function-header",
            expected_code="D002",
            files={
                "functions/sql/is_placed.sql": (
                    'FUNCTION (\n  description "Whether placed",\n  returns,\n);\n\n'
                    "order_status = 'placed'\n"
                )
            },
        ),
        _case(
            name="column-nullable-not-null",
            expected_code="P002",
            files={
                FAILURE_STAGING_PATH: FAILURE_BASE_STAGING.replace(
                    '"Staged orders",',
                    '"Staged orders",\n  columns (\n'
                    "    order_id (nullable true, audits [not_null]),\n  ),",
                )
            },
        ),
    )


def _layout_cases() -> tuple[FailureCase, ...]:
    return tuple(
        _case(name=name, expected_code="D013", files={path: contents})
        for name, path, contents in (
            ("scoped-root-at-project-root", "_enums/order_status.sql", ""),
            ("declaration-group-below-root", "models/_sqlbuild/macros/money.py", _MACRO_MODULE),
            ("declaration-root-nested", "models/marts/_enums/_constants/limits.sql", ""),
            ("declaration-group-unsupported-entry", "models/marts/_sqlbuild/notes.txt", ""),
            ("named-role-nested-declaration", "schemas/enums/order_status.sql", ""),
            ("audit-role-unsupported-entry", "audits/at_least.sql", ""),
            ("local-singular-audit", "models/marts/_sqlbuild/_audits/singular/at_least.sql", ""),
            ("hook-role-unsupported-entry", "models/marts/_sqlbuild/hooks/notes.sql", ""),
        )
    )


def _yaml_file_cases() -> tuple[FailureCase, ...]:
    return (
        _case(
            name="schema-yml-model-metadata",
            expected_code="D005",
            files={
                "models/marts/schema.yml": (
                    "models:\n  - name: customer_totals\n    description: Totals.\n"
                )
            },
        ),
        _case(
            name="seed-yaml-extension",
            expected_code="D005",
            files={
                "seeds/order_channels.yaml": _SEED_DECLARATION,
                "seeds/order_channels.csv": "id,label\n1,web\n",
            },
        ),
        _case(
            name="source-unknown-key",
            expected_code="D006",
            files={
                FAILURE_SOURCES_PATH: FAILURE_BASE_FILES[FAILURE_SOURCES_PATH].replace(
                    "    description: Orders feed.\n",
                    "    description: Orders feed.\n    freshnes: 1d\n",
                )
            },
        ),
        _case(
            name="seed-declaration-without-csv",
            expected_code="D008",
            files={"seeds/order_channels.yml": _SEED_DECLARATION},
        ),
        _case(
            name="seed-header-mismatch",
            expected_code="D008",
            files={
                "seeds/order_channels.yml": _SEED_DECLARATION,
                "seeds/order_channels.csv": "id,name\n1,web\n",
            },
        ),
    )


def _conflict_cases() -> tuple[FailureCase, ...]:
    return (
        _case(
            name="duplicate-source",
            expected_code="D007",
            files={"sources/more.yml": FAILURE_BASE_FILES[FAILURE_SOURCES_PATH]},
        ),
        _case(
            name="duplicate-scenario",
            expected_code="D007",
            files={
                f"tests/scenarios/{folder}/orders.sql": (
                    'SCENARIO (description "Orders world");\n\n'
                    "WITH\n__source__raw_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    "__expected__stg_orders AS (\n  SELECT 1 AS order_id\n)\nSELECT 1\n"
                )
                for folder in ("north", "south")
            },
        ),
        _case(
            name="resource-name-collision",
            expected_code="D007",
            files={
                "seeds/stg_orders.yml": _SEED_DECLARATION.replace("order_channels", "stg_orders"),
                "seeds/stg_orders.csv": "id,label\n1,web\n",
            },
        ),
        _case(
            name="managed-source-without-loader",
            expected_code="D007",
            files={
                FAILURE_SOURCES_PATH: FAILURE_BASE_FILES[FAILURE_SOURCES_PATH]
                + "  - name: loaded_products\n    description: Loaded products.\n"
                "    managed: true\n    write_strategy: table\n"
                "    columns:\n      - name: id\n        type: INTEGER\n"
            },
        ),
        _case(
            name="duplicate-python-node",
            expected_code="D007",
            files={
                "python/tasks/first.py": _TASK_MODULE,
                "python/tasks/second.py": _TASK_MODULE,
            },
        ),
        _case(
            name="check-depends-on-check",
            expected_code="D007",
            files={
                "python/checks/orders.py": (
                    "from sqlbuild.checks import check\nfrom sqlbuild.refs import model\n\n\n"
                    '@check(depends_on=model("stg_orders"))\ndef orders_present(ctx):\n'
                    '    """Orders present."""\n    return ctx.pass_()\n\n\n'
                    "@check(depends_on=orders_present)\ndef orders_checked(ctx):\n"
                    '    """Orders checked."""\n    return ctx.pass_()\n'
                )
            },
        ),
    )


def _python_cases() -> tuple[FailureCase, ...]:
    return (
        _case(
            name="python-node-import-error",
            expected_code="D011",
            files={"python/tasks/exports.py": "import missing_orders_client\n" + _TASK_MODULE},
        ),
        _case(
            name="duplicate-hook",
            expected_code="D011",
            files={
                "hooks/python/first.py": _HOOK_MODULE,
                "hooks/python/second.py": _HOOK_MODULE,
            },
        ),
        _case(
            name="provider-invalid-settings",
            expected_code="D012",
            files={
                "providers/export_settings.py": (
                    "from sqlbuild.providers import Provider\n\n\n"
                    "class ExportSettings(Provider):\n"
                    '    """Export settings."""\n\n'
                    "    api_token: str\n"
                )
            },
        ),
        _case(
            name="duplicate-provider",
            expected_code="D012",
            files={
                f"providers/{module}.py": (
                    "from sqlbuild.providers import Provider\n\n\n"
                    "class ExportSettings(Provider):\n"
                    '    """Export settings."""\n\n'
                    '    region: str = "north"\n'
                )
                for module in ("first", "second")
            },
        ),
        _case(
            name="legacy-event-exporters-directory",
            expected_code="D015",
            files={"event_exporters/publish.py": "VALUE = 1\n"},
        ),
        _case(
            name="lifecycle-sink-default-parameter",
            expected_code="D015",
            files={
                "sinks/lifecycle.py": (
                    "from sqlbuild.sinks import LifecycleEvent, lifecycle_event_sink\n\n\n"
                    "@lifecycle_event_sink()\n"
                    "def ignore_events(event: LifecycleEvent, limit=3) -> None:\n"
                    "    return None\n"
                )
            },
        ),
        _case(
            name="lifecycle-sink-unknown-provider",
            expected_code="D015",
            files={
                "sinks/lifecycle.py": (
                    "from sqlbuild.sinks import LifecycleEvent, lifecycle_event_sink\n\n\n"
                    "@lifecycle_event_sink()\n"
                    "def publish_events(event: LifecycleEvent, destination_client) -> None:\n"
                    "    return None\n"
                )
            },
        ),
        _case(
            name="command-output-sink-unknown-provider",
            expected_code="D015",
            files={
                "sinks/output.py": (
                    "from sqlbuild.sinks import CommandOutputRecord, command_output_sink\n\n\n"
                    '@command_output_sink(streams={"stdout"})\n'
                    "def publish_output(record: CommandOutputRecord, destination_client) -> None:\n"
                    "    return None\n"
                )
            },
        ),
        _case(
            name="materialization-import-error",
            expected_code="D011",
            files={
                "materializations/copy_table.py": "import missing_warehouse_client\n",
                FAILURE_MART_PATH: FAILURE_BASE_MART.replace(
                    '"Order totals per customer",',
                    '"Order totals per customer",\n  materialized copy_table,',
                ),
            },
        ),
        _case(
            name="python-outside-extension-root",
            expected_code="D016",
            files={"helpers/formatting.py": "VALUE = 1\n"},
        ),
    )
