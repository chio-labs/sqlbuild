"""Minimal projects that fail while rendering, scoping, or attaching compile inputs."""

from scripts.compiler_differential._helpers.corpus.case_builder import (
    config_files,
    failure_case,
    mart_body_files,
    staging_files,
)
from scripts.compiler_differential.constants import (
    FAILURE_BASE_MART,
    FAILURE_BASE_STAGING,
    FAILURE_MART_PATH,
    GENERATOR_MISSING_ENV_VAR,
)
from scripts.compiler_differential.models import FailureCase

_STAGING_HEADER: str = '"Staged orders",'
_MART_HEADER: str = '"Order totals per customer",'
_STAGING_COLUMNS: str = "amount, status"
_STAGING_MACROS: str = "models/staging/_sqlbuild/_macros/orders.py"
_MART_MACROS: str = "models/marts/_sqlbuild/_macros/orders.py"
_CENTS_MACRO: str = (
    'def cents(expression: str) -> str:\n    """Convert to cents."""\n'
    '    return f"({expression} * 100)"\n'
)
_ORDERS_FOR: str = (
    "FUNCTION (\n"
    '  description "Orders for one customer",\n'
    "  arguments (p_customer INTEGER),\n"
    "  returns table (\n    order_id INTEGER\n  ),\n);\n\n"
    'SELECT order_id\nFROM __ref("stg_orders")\nWHERE customer_id = p_customer\n'
)
_FLOOR_AUDIT: str = 'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE amount < @minimum\n'
_RECORD_HOOK: str = "HOOK (\n  description \"Record a refresh\"\n);\n\nSELECT @'label' AS label\n"
_TOTALS_READER: str = (
    'AUDIT ();\n\nSELECT *\nFROM __ref("@model") o\n'
    'WHERE o.customer_id NOT IN (SELECT customer_id FROM __ref("customer_totals"))\n'
)
_HOOK_READING_TOTALS: str = (
    "from sqlbuild.hooks import hook\nfrom sqlbuild.refs import model\n\n\n"
    '@hook(reads=[model("customer_totals")])\n'
    'def note_refresh(ctx):\n    """Note a refresh."""\n    return None\n'
)
_UPSTREAM_DBT_PROJECT: str = "name: upstream\nversion: '1.0.0'\nprofile: upstream\n"


def _staging_header(extra: str) -> dict[str, str]:
    return staging_files(
        FAILURE_BASE_STAGING.replace(_STAGING_HEADER, f"{_STAGING_HEADER}\n{extra}")
    )


def _staging_columns(*, columns: str, files: dict[str, str] | None = None) -> dict[str, str]:
    return {
        **(files or {}),
        **staging_files(FAILURE_BASE_STAGING.replace(_STAGING_COLUMNS, columns, 1)),
    }


def render_failure_cases() -> tuple[FailureCase, ...]:
    """Return the render-time failure cases in a stable order."""

    return (
        *_macro_cases(),
        *_interpolation_cases(),
        *_reference_cases(),
        *_attachment_cases(),
        *_model_config_cases(),
    )


def _macro_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="macro-returns-non-string",
            expected_code="P001",
            expected_message="must return a SQL string",
            files=_staging_columns(
                columns="amount, status, @answer() AS answer",
                files={
                    _STAGING_MACROS: (
                        'def answer() -> int:\n    """Return a number."""\n    return 42\n'
                    )
                },
            ),
        ),
        failure_case(
            name="macro-output-calls-macro",
            expected_code="P001",
            expected_message="returned SQLBuild call(s) @cents()",
            files=_staging_columns(
                columns='amount, status, @wrapped("amount") AS wrapped',
                files={
                    _STAGING_MACROS: _CENTS_MACRO
                    + '\n\ndef wrapped(expression: str) -> str:\n    """Wrap a call."""\n'
                    + "    return f'@cents(\"{expression}\")'\n"
                },
            ),
        ),
        failure_case(
            name="macro-non-literal-argument",
            expected_code="P001",
            expected_message="must use only Python literals",
            files=_staging_columns(
                columns="amount, status, @cents(amount) AS cents",
                files={_STAGING_MACROS: _CENTS_MACRO},
            ),
        ),
        failure_case(
            name="macro-in-sibling-scope",
            expected_code="P001",
            expected_message="is inaccessible",
            files=_staging_columns(
                columns='amount, status, @cents("amount") AS cents',
                files={_MART_MACROS: _CENTS_MACRO},
            ),
        ),
        failure_case(
            name="local-macro-needed-below-owner",
            expected_code="S007",
            files={
                _STAGING_MACROS: _CENTS_MACRO,
                "models/staging/_sqlbuild/macros/wrapping.py": (
                    "from models.staging._sqlbuild._macros.orders import cents\n\n\n"
                    'def wrapped(expression: str) -> str:\n    """Wrap cents."""\n'
                    "    return cents(expression)\n"
                ),
                "models/staging/regional/stg_regional_orders.sql": (
                    'MODEL (\n  description "Regional orders",\n);\n\n'
                    'SELECT order_id, @wrapped("amount") AS amount_cents\n'
                    'FROM __ref("stg_orders")\n'
                ),
            },
        ),
    )


def _interpolation_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="unset-environment-variable",
            expected_code="P001",
            expected_message="unknown environment variable '@@ENV:SQB_DIFFERENTIAL_UNSET'",
            files=_staging_columns(
                columns="amount, status, '@@ENV:SQB_DIFFERENTIAL_UNSET' AS channel"
            ),
        ),
        failure_case(
            name="unclosed-dollar-quote-with-project-variable",
            expected_code="P001",
            expected_message="SQL interpolation contains an unclosed quoted string",
            files={
                **config_files('\n[vars]\nregion = "north"\n'),
                **_staging_columns(columns="amount, status, $tag$ @@region AS region"),
            },
        ),
        failure_case(
            name="context-variable-in-model-sql",
            expected_code="P001",
            expected_message="does not allow @@CTX templates",
            files=_staging_columns(
                columns="amount, status, '@@CTX:destination.qualified' AS destination"
            ),
        ),
        failure_case(
            name="runtime-placeholder-without-default",
            expected_code="P001",
            expected_message="@@@placeholders without default values",
            files={
                "materializations/copy_table.py": (
                    "from sqlbuild.executor.custom.models import MaterializationContext, "
                    "MaterializationResult\n\n\n"
                    "def materialize(ctx: MaterializationContext) -> MaterializationResult:\n"
                    "    return MaterializationResult(relation=ctx.destination, audit_results=())\n"
                ),
                **staging_files(
                    FAILURE_BASE_STAGING.replace(
                        _STAGING_HEADER, f"{_STAGING_HEADER}\n  materialized copy_table,"
                    ).replace(
                        _STAGING_COLUMNS,
                        "amount, status, CAST(@@@window_start AS DATE) AS window_start",
                    )
                ),
            },
        ),
        failure_case(
            name="cursor-intrinsic-outside-incremental",
            expected_code="P001",
            expected_message="uses cursor intrinsics but is not a built-in incremental model",
            files=_staging_columns(columns="amount, status, __cursor_start() AS window_start"),
        ),
        failure_case(
            name="named-hook-missing-argument",
            expected_code="P001",
            expected_message="is missing argument 'label'",
            files={
                "hooks/sql/record_refresh.sql": _RECORD_HOOK,
                FAILURE_MART_PATH: FAILURE_BASE_MART.replace(
                    _MART_HEADER, f'{_MART_HEADER}\n  post_hooks [sql("record_refresh")],'
                ),
            },
        ),
        failure_case(
            name="generic-audit-missing-argument",
            expected_code="P001",
            expected_message="is missing argument 'minimum' for generic audit 'floor'",
            files={
                "models/staging/_sqlbuild/_audits/generic/floor.sql": _FLOOR_AUDIT,
                **_staging_header("  audits [floor],"),
            },
        ),
    )


def _reference_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="table-function-arity",
            expected_code="P001",
            expected_message="expects 1 argument but received 2",
            files={
                "functions/sql/table_fn__orders_for.sql": _ORDERS_FOR,
                **mart_body_files(
                    "SELECT order_id AS customer_id, 1 AS total_amount\n"
                    'FROM __table_fn("table_fn__orders_for")(1, 2)\n'
                ),
            },
        ),
        failure_case(
            name="unknown-table-function",
            expected_code="P001",
            expected_message="references unknown table function 'table_fn__missing'",
            files=mart_body_files(
                "SELECT order_id AS customer_id, 1 AS total_amount\n"
                'FROM __table_fn("table_fn__missing")(1)\n'
            ),
        ),
        failure_case(
            name="unknown-scalar-function",
            expected_code="P001",
            expected_message="references unknown SQL function 'is_large'",
            files=_staging_columns(columns='amount, status, __udf("is_large")(amount) AS is_large'),
        ),
        failure_case(
            name="test-expects-unknown-model",
            expected_code="P001",
            expected_message="expects unknown model 'stg_payments'",
            files={
                "tests/unit/test_stg_payments.sql": (
                    "TEST();\n\nWITH\n__source__raw_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    "__expected__stg_payments AS (\n  SELECT 1 AS order_id\n)\nSELECT 1\n"
                )
            },
        ),
        failure_case(
            name="test-helper-reads-unknown-model",
            expected_code="P013",
            expected_message="SQL test helper CTE 'archived_orders' references unknown model",
            files={
                "tests/unit/test_stg_orders.sql": (
                    "TEST();\n\nWITH\n__source__raw_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    'archived_orders AS (\n  SELECT order_id FROM __ref("archived_orders")\n),\n'
                    "__assert__no_archived_orders AS (\n"
                    '  SELECT order_id FROM __ref("stg_orders")\n'
                    "  JOIN archived_orders USING (order_id)\n"
                    ")\nSELECT 1\n"
                )
            },
        ),
        failure_case(
            name="test-assertion-reads-unmocked-source",
            expected_code="P013",
            expected_message=(
                "SQL test assertion CTE '__assert__no_negative_orders' calls "
                '__source("raw_orders"), which the test does not mock'
            ),
            files={
                "tests/unit/test_customer_totals.sql": (
                    "TEST();\n\nWITH\n__ref__stg_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    "__expected__customer_totals AS (\n"
                    "  SELECT 10 AS customer_id, CAST(5 AS DOUBLE) AS total_amount\n),\n"
                    "__assert__no_negative_orders AS (\n"
                    '  SELECT order_id FROM __source("raw_orders") WHERE amount < 0\n'
                    ")\nSELECT 1\n"
                )
            },
        ),
        failure_case(
            name="test-reads-only-mocks",
            expected_code="P013",
            expected_message=(
                "SQL test 'test_stg_orders' mocks the model it tests (__ref__stg_orders), so "
                "the test has no model to run against"
            ),
            files={
                "tests/unit/test_stg_orders.sql": (
                    "TEST();\n\nWITH\n__ref__stg_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    "__assert__no_negative_amounts AS (\n"
                    '  SELECT order_id FROM __ref("stg_orders") WHERE amount < 0\n'
                    ")\nSELECT 1\n"
                )
            },
        ),
        failure_case(
            name="test-expected-reads-unknown-model",
            expected_code="P013",
            expected_message=(
                "SQL test expected CTE '__expected__stg_orders' references unknown model "
                "'archived_orders'"
            ),
            files={
                "tests/unit/test_stg_orders.sql": (
                    "TEST();\n\nWITH\n__source__raw_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    "__expected__stg_orders AS (\n"
                    '  SELECT order_id FROM __ref("archived_orders")\n'
                    ")\nSELECT 1\n"
                )
            },
        ),
        failure_case(
            name="dbt-reference-without-manifest",
            expected_code="C214",
            files={
                **config_files('\n[dbt]\nproject_dir = "dbt"\n'),
                "dbt/dbt_project.yml": _UPSTREAM_DBT_PROJECT,
                **mart_body_files(
                    "SELECT customer_id, COUNT(*) AS order_count\n"
                    'FROM __dbt_ref("upstream", "upstream_orders")\nGROUP BY customer_id\n'
                ),
            },
        ),
        failure_case(
            name="hard-coded-relation-in-python",
            expected_code="P008",
            files={
                "python/tasks/exports.py": (
                    "from sqlbuild.tasks import task\n\n\n"
                    '@task\ndef export_orders(ctx):\n    """Export orders."""\n'
                    '    return ctx.query("SELECT * FROM stg_orders")\n'
                )
            },
        ),
    )


def _attachment_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="attached-audit-reads-dependant",
            expected_code="P005",
            files={
                "models/staging/_sqlbuild/_audits/generic/matches_totals.sql": _TOTALS_READER,
                **_staging_header("  audits [matches_totals],"),
            },
        ),
        failure_case(
            name="hook-reads-dependant",
            expected_code="P007",
            files={
                "models/staging/_sqlbuild/_hooks/python/notes.py": _HOOK_READING_TOTALS,
                **_staging_header('  post_hooks [python("note_refresh")],'),
            },
        ),
        failure_case(
            name="unneeded-sql-analysis-opt-out",
            expected_code="P009",
            files={
                **config_files("\n[settings]\nrequire_sql_analysis = true\n"),
                **_staging_header("  sql_analysis false,"),
            },
        ),
        failure_case(
            name="snapshot-schema-change-with-contract",
            expected_code="K012",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n  materialized snapshot,\n'
                "  unique_key [order_id],\n  snapshot_strategy check,\n"
                "  check_columns [status],\n  snapshot_schema_change append_new_columns,\n"
                "  contract enforced,\n  columns (\n    order_id (type INTEGER),\n"
                "    customer_id (type INTEGER),\n    amount (type DOUBLE),\n"
                "    status (type VARCHAR),\n  ),\n);\n\n"
                'SELECT order_id, customer_id, amount, status\nFROM __source("raw_orders")\n'
            ),
        ),
        failure_case(
            name="schema-from-sibling-folder",
            expected_code="S006",
            files={
                "models/marts/_sqlbuild/_schemas/order_shape.sql": (
                    'SCHEMA (\n  name order_shape,\n  description "Order shape",\n'
                    "  columns (\n    order_id (type INTEGER),\n  ),\n);\n"
                ),
                **_staging_header("  model_schema order_shape,"),
            },
        ),
        failure_case(
            name="inherited-declaration-used-in-one-folder",
            expected_code="S008",
            files={
                "models/staging/_sqlbuild/constants/limits.sql": (
                    "CONSTANT (name minimum_amount, value 1);\n"
                ),
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
            },
        ),
        failure_case(
            name="singular-audit-across-trees",
            expected_code="S009",
            files={
                "models/marts/_sqlbuild/audits/singular/totals_have_orders.sql": (
                    'AUDIT (name "totals_have_orders");\n\n'
                    'SELECT t.customer_id\nFROM __ref("customer_totals") t\n'
                    'LEFT JOIN __source("raw_orders") o ON t.customer_id = o.customer_id\n'
                    "WHERE o.customer_id IS NULL\n"
                )
            },
        ),
        failure_case(
            name="orphan-audit-factory",
            expected_code="S024",
            expected_warning_code="C216",
            files={
                "python/audits/quality.py": (
                    "from sqlbuild.audits import AuditCase, audit_factory\n\n\n"
                    "@audit_factory\ndef order_quality():\n"
                    '    return [AuditCase(name="id_present", definition="not_null", '
                    'arguments={"column": "order_id"})]\n'
                ),
                "constants/limits.sql": "CONSTANT (name minimum_amount, value 1);\n",
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
            },
        ),
    )


def _model_config_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="model-column-audit-unknown-severity",
            expected_code="P001",
            expected_message="severity",
            files=_staging_header("  columns (amount (audits [not_null (severity fatal)])),"),
        ),
        failure_case(
            name="model-duplicate-column",
            expected_code="P001",
            expected_message="duplicate",
            files=_staging_header("  columns (amount (type DOUBLE), AMOUNT (type DOUBLE)),"),
        ),
        failure_case(
            name="model-blank-column-type",
            expected_code="P001",
            expected_message="non-empty string",
            files=_staging_header('  columns (amount (type " ")),'),
        ),
        failure_case(
            name="model-nullable-column-with-not-null",
            expected_code="P002",
            expected_message="not_null",
            files=_staging_header("  columns (amount (nullable true, audits [not_null])),"),
        ),
        failure_case(
            name="model-template-missing-environment",
            expected_code="P001",
            expected_message="missing ENV variable",
            files=_staging_header(f'  schema "${{ENV:{GENERATOR_MISSING_ENV_VAR}}}",'),
        ),
        failure_case(
            name="model-template-unknown-function",
            expected_code="P001",
            expected_message="unsupported template function",
            files=_staging_header("  schema \"${upper('orders')}\","),
        ),
        failure_case(
            name="model-template-unterminated-string",
            expected_code="P001",
            expected_message="unterminated",
            files=_staging_header('  schema "${coalesce(\'orders)}",'),
        ),
    )
