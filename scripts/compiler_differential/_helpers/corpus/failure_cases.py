"""Minimal failing projects, each derived from the shared base project."""

from scripts.compiler_differential._helpers.corpus.case_builder import (
    failure_case,
    mart_body_files,
    staging_files,
)
from scripts.compiler_differential._helpers.corpus.discovery_failure_cases import (
    discovery_failure_cases,
)
from scripts.compiler_differential._helpers.corpus.reference_failure_cases import (
    reference_failure_cases,
)
from scripts.compiler_differential._helpers.corpus.render_failure_cases import (
    render_failure_cases,
)
from scripts.compiler_differential._helpers.corpus.scope_failure_cases import (
    scope_failure_cases,
)
from scripts.compiler_differential.constants import (
    FAILURE_BASE_CONFIG,
    FAILURE_BASE_MART,
    FAILURE_BASE_STAGING,
    FAILURE_CONFIG_PATH,
    FAILURE_MART_PATH,
    FAILURE_SOURCES_PATH,
)
from scripts.compiler_differential.models import FailureCase

_RULES_CONFIG: str = '\n[rules]\nselect = ["{codes}"]\n'


def _rules(*codes: str) -> dict[str, str]:
    return {
        FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG + _RULES_CONFIG.format(codes='", "'.join(codes))
    }


def all_failure_cases() -> tuple[FailureCase, ...]:
    """Return every failure case in a stable order."""

    return (
        *_compile_failure_cases(),
        *discovery_failure_cases(),
        *render_failure_cases(),
        *scope_failure_cases(),
        *reference_failure_cases(),
    )


def _compile_failure_cases() -> tuple[FailureCase, ...]:
    return (
        failure_case(
            name="config-toml-syntax",
            expected_code="D001",
            files={
                FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG + "[defaults\nmaterialized = 'table'\n"
            },
        ),
        failure_case(
            name="config-unknown-default-key",
            expected_code="D001",
            files={
                FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG + '\n[defaults]\ndescription = "Shared"\n'
            },
        ),
        failure_case(
            name="config-unknown-adapter",
            expected_code="C601",
            files={FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG.replace('"duckdb"', '"warehouse9000"')},
        ),
        failure_case(
            name="model-header-syntax",
            expected_code="D002",
            files=staging_files(
                FAILURE_BASE_STAGING.replace(
                    '"Staged orders",', '"Staged orders",\n  materialized (,'
                )
            ),
        ),
        failure_case(
            name="model-sql-syntax",
            expected_code="P001",
            files=staging_files(
                FAILURE_BASE_STAGING.replace("SELECT order_id,", "SELECT order_id,, ")
            ),
        ),
        failure_case(
            name="test-parse",
            expected_code="D003",
            files={"tests/unit/test_stg_orders.sql": "TEST(\n\nSELECT 1\n"},
        ),
        failure_case(
            name="audit-parse",
            expected_code="D004",
            files={
                "models/marts/_sqlbuild/audits/singular/broken.sql": "AUDIT (name);\n\nSELECT 1\n"
            },
        ),
        failure_case(
            name="schema-unterminated-declaration",
            expected_code="D013",
            files={"models/staging/_sqlbuild/_schemas/orders.sql": "SCHEMA (\n  name orders,\n"},
        ),
        failure_case(
            name="source-parse",
            expected_code="D006",
            files={FAILURE_SOURCES_PATH: "sources:\n  - name: raw_orders\n    columns: [\n"},
        ),
        failure_case(
            name="duplicate-model",
            expected_code="D007",
            files={"models/marts/stg_orders.sql": FAILURE_BASE_STAGING},
        ),
        failure_case(
            name="seed-without-header",
            expected_code="D008",
            files={"seeds/lookups.csv": ""},
        ),
        failure_case(
            name="scenario-parse",
            expected_code="D009",
            files={"tests/scenarios/orders.sql": "SCENARIO (\n\nSELECT 1\n"},
        ),
        failure_case(
            name="python-node-missing-description",
            expected_code="P010",
            files={
                "python/tasks/exports.py": (
                    "from sqlbuild.tasks import TaskContext, task\n\n\n"
                    "@task\ndef export_orders(ctx: TaskContext):\n    return None\n"
                )
            },
        ),
        failure_case(
            name="enum-parse",
            expected_code="D013",
            files={"enums/order_status.sql": "ENUM (\n  name order_status,\n  members [,\n);\n"},
        ),
        failure_case(
            name="hook-without-header",
            expected_code="D014",
            files={"hooks/sql/record_refresh.sql": "SELECT 1\n"},
        ),
        failure_case(
            name="invalid-resource-name",
            expected_code="D016",
            files={"models/marts/order-totals.sql": FAILURE_BASE_MART},
        ),
        failure_case(
            name="built-in-audit-shadow",
            expected_code="S010",
            expected_warning_code="P003",
            files={
                "models/staging/_sqlbuild/_audits/generic/not_null.sql": (
                    'AUDIT (name "not_null");\n\nSELECT 1 WHERE FALSE\n'
                )
            },
        ),
        failure_case(
            name="singular-audit-one-resource",
            expected_code="P004",
            files={
                "models/marts/_sqlbuild/audits/singular/positive_totals.sql": (
                    'AUDIT (name "positive_totals");\n\n'
                    'SELECT customer_id FROM __ref("customer_totals") WHERE total_amount < 0\n'
                )
            },
        ),
        failure_case(
            name="macro-generated-reference",
            expected_code="P006",
            files={
                "models/marts/_sqlbuild/_macros/orders.py": (
                    "def staged_orders() -> str:\n"
                    '    """Return the staged orders relation."""\n'
                    "    return '__ref(\"stg_orders\")'\n"
                ),
                **mart_body_files(
                    "SELECT customer_id, SUM(amount) AS total_amount\n"
                    "FROM @staged_orders()\nGROUP BY customer_id\n"
                ),
            },
        ),
        failure_case(
            name="missing-description",
            expected_code="P010",
            files=staging_files(
                FAILURE_BASE_STAGING.replace('  description "Staged orders",\n', "")
            ),
        ),
        failure_case(
            name="unknown-ref",
            expected_code="P001",
            files=mart_body_files(
                'SELECT customer_id, SUM(amount) AS total_amount\nFROM __ref("stg_payments")\n'
                "GROUP BY customer_id\n"
            ),
        ),
        failure_case(
            name="unknown-source",
            expected_code="P001",
            files=staging_files(
                FAILURE_BASE_STAGING.replace('__source("raw_orders")', '__source("raw_payments")')
            ),
        ),
        failure_case(
            name="unknown-macro",
            expected_code="P001",
            files=staging_files(
                FAILURE_BASE_STAGING.replace("amount, status", '@cents("amount") AS amount, status')
            ),
        ),
        failure_case(
            name="failing-macro",
            expected_code="P001",
            files={
                "models/staging/_sqlbuild/_macros/cents.py": (
                    "def cents(expression: str) -> str:\n"
                    '    """Refuse every input."""\n'
                    '    raise ValueError(f"cannot convert {expression}")\n'
                ),
                **staging_files(
                    FAILURE_BASE_STAGING.replace(
                        "amount, status", '@cents("amount") AS amount, status'
                    )
                ),
            },
        ),
        failure_case(
            name="unknown-enum-member",
            expected_code="P001",
            files={
                "models/staging/_sqlbuild/_enums/order_status.sql": (
                    "ENUM (\n  name order_status,\n  members [PLACED, SHIPPED],\n);\n"
                ),
                **staging_files(
                    FAILURE_BASE_STAGING + 'WHERE status = @enum("order_status").RETURNED\n'
                ),
            },
        ),
        failure_case(
            name="unknown-constant",
            expected_code="P001",
            files=staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
        ),
        failure_case(
            name="invalid-decimal-constant",
            expected_code="D013",
            files={
                "models/staging/_sqlbuild/_constants/limits.sql": (
                    'CONSTANT (name minimum_amount, type decimal, value "ten");\n'
                ),
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
            },
        ),
        failure_case(
            name="duplicate-declaration",
            expected_code="P001",
            files={
                "models/staging/_sqlbuild/_constants/limits.sql": (
                    "CONSTANT (name minimum_amount, value 1);\n"
                    "CONSTANT (name minimum_amount, value 2);\n"
                ),
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
            },
        ),
        failure_case(
            name="inaccessible-declaration",
            expected_code="P001",
            files={
                "models/marts/_sqlbuild/_constants/limits.sql": (
                    "CONSTANT (name minimum_amount, value 1);\n"
                ),
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
            },
        ),
        failure_case(
            name="over-broad-global",
            expected_code="S024",
            files={
                "constants/limits.sql": "CONSTANT (name minimum_amount, value 1);\n",
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("minimum_amount")\n'),
            },
        ),
        failure_case(
            name="unused-declaration",
            expected_code="S010",
            files={
                "models/staging/_sqlbuild/_constants/limits.sql": (
                    "CONSTANT (name spare, value 1);\n"
                )
            },
        ),
        failure_case(
            name="macro-import-cycle",
            expected_code="P001",
            files={
                "macros/first.py": (
                    "from macros.second import second_value\n\n\n"
                    "def first_value() -> str:\n"
                    '    """First value."""\n'
                    "    return second_value()\n"
                ),
                "macros/second.py": (
                    "from macros.first import first_value\n\n\n"
                    "def second_value() -> str:\n"
                    '    """Second value."""\n'
                    "    return first_value()\n"
                ),
            },
        ),
        failure_case(
            name="contract-missing-column",
            expected_code="K001",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n  contract enforced,\n'
                "  columns (\n    order_id (type INTEGER),\n    customer_id (type INTEGER),\n"
                "    amount (type DOUBLE),\n    status (type VARCHAR),\n"
                "    discount (type DOUBLE),\n"
                "  ),\n);\n\n"
                'SELECT order_id, customer_id, amount, status\nFROM __source("raw_orders")\n'
            ),
        ),
        failure_case(
            name="contract-type-mismatch",
            expected_code="K002",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n  contract enforced,\n'
                "  columns (\n    order_id (type VARCHAR),\n    customer_id (type INTEGER),\n"
                "    amount (type DOUBLE),\n    status (type VARCHAR),\n  ),\n);\n\n"
                'SELECT order_id, customer_id, amount, status\nFROM __source("raw_orders")\n'
            ),
        ),
        failure_case(
            name="set-operation-width",
            expected_code="B216",
            files=mart_body_files(
                'SELECT customer_id, amount FROM __ref("stg_orders")\n'
                'UNION ALL\nSELECT customer_id FROM __ref("stg_orders")\n'
            ),
        ),
        failure_case(
            name="comparison-type",
            expected_code="B217",
            files=mart_body_files(
                "SELECT customer_id, SUM(amount) AS total_amount\n"
                "FROM __ref(\"stg_orders\")\nWHERE amount = DATE '2026-01-01'\n"
                "GROUP BY customer_id\n"
            ),
        ),
        failure_case(
            name="unknown-column",
            expected_code="B002",
            files=mart_body_files(
                'SELECT customer_id, SUM(discount) AS total_amount\nFROM __ref("stg_orders")\n'
                "GROUP BY customer_id\n"
            ),
        ),
        failure_case(
            name="ungrouped-column",
            expected_code="B230",
            files=mart_body_files(
                "SELECT customer_id, status, SUM(amount) AS total_amount\n"
                'FROM __ref("stg_orders")\n'
                "GROUP BY customer_id\n"
            ),
        ),
        failure_case(
            name="test-expected-unknown-column",
            expected_code="B302",
            files={
                "tests/unit/test_stg_orders.sql": (
                    "TEST();\n\nWITH\n__source__raw_orders AS (\n"
                    "  SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount,"
                    " 'placed' AS status\n),\n"
                    "__expected__stg_orders AS (\n  SELECT 1 AS order_id, 2 AS discount\n)\n"
                    "SELECT 1\n"
                )
            },
        ),
        failure_case(
            name="rule-unused-cte",
            expected_code="SQBRSQL005",
            files={
                **_rules("SQBRSQL005"),
                **mart_body_files(
                    "WITH spare AS (SELECT 1 AS one)\n"
                    "SELECT customer_id, SUM(amount) AS total_amount\n"
                    'FROM __ref("stg_orders")\nGROUP BY customer_id\n'
                ),
            },
        ),
        failure_case(
            name="rule-custom-finding",
            expected_code="XSQBRDIFF001",
            files={
                FAILURE_CONFIG_PATH: FAILURE_BASE_CONFIG
                + '\n[rules]\nselect = ["XSQBR"]\n\n'
                + "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
                "rules/no_staging.py": (
                    "from sqlbuild.rules import Finding, Model, RuleContext, rule\n\n\n"
                    '@rule(code="XSQBRDIFF001", message="Models avoid the stg_ prefix", '
                    'remediation="Rename the model.")\n'
                    "def no_staging_prefix(*, model: Model, ctx: RuleContext) -> list[Finding]:\n"
                    '    if not model.name.startswith("stg_"):\n'
                    "        return []\n"
                    "    return [ctx.finding(subject=model)]\n"
                ),
            },
        ),
        failure_case(
            name="multiple-errors-order",
            expected_code="P010",
            files={
                **staging_files(
                    FAILURE_BASE_STAGING.replace('  description "Staged orders",\n', "")
                ),
                FAILURE_MART_PATH: FAILURE_BASE_MART.replace(
                    '  description "Order totals per customer",\n', ""
                ),
                "models/marts/order_counts.sql": (
                    "MODEL ();\n\nSELECT customer_id, COUNT(*) AS order_count\n"
                    'FROM __ref("stg_orders")\nGROUP BY customer_id\n'
                ),
            },
        ),
        failure_case(
            name="contract-extra-column",
            expected_code="K005",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n  contract enforced,\n'
                "  columns (\n    order_id (type INTEGER),\n    customer_id (type INTEGER),\n"
                "    amount (type DOUBLE),\n  ),\n);\n\n"
                'SELECT order_id, customer_id, amount, status\nFROM __source("raw_orders")\n'
            ),
        ),
        failure_case(
            name="contract-unknown-type",
            expected_code="K002",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n'
                "  columns (\n    order_id (type MYSTERY_TYPE),\n  ),\n);\n\n"
                'SELECT order_id, customer_id, amount, status\nFROM __source("raw_orders")\n'
            ),
        ),
        failure_case(
            name="cursor-unknown-column",
            expected_code="B300",
            files=mart_body_files(
                "SELECT customer_id, SUM(amount) AS total_amount\n"
                'FROM __ref("stg_orders")\nGROUP BY customer_id\n'
            )
            | {
                FAILURE_MART_PATH: (
                    'MODEL (\n  description "Order totals per customer",\n'
                    "  materialized incremental,\n  incremental_strategy delete_insert,\n"
                    "  cursor placed_at,\n  cursor_type timestamp,\n  cursor_grain day,\n"
                    "  cursor_inputs (\n    stg_orders order_id,\n  ),\n);\n\n"
                    "SELECT customer_id, SUM(amount) AS total_amount\n"
                    'FROM __ref("stg_orders")\nGROUP BY customer_id\n'
                )
            },
        ),
        failure_case(
            name="cursor-model-without-inputs",
            expected_code="P011",
            files={
                FAILURE_MART_PATH: (
                    'MODEL (\n  description "Order totals per customer",\n'
                    "  materialized incremental,\n  incremental_strategy delete_insert,\n"
                    "  cursor placed_at,\n  cursor_type timestamp,\n  cursor_grain day,\n);\n\n"
                    "SELECT TIMESTAMP '2026-01-01 00:00:00' AS placed_at, 1 AS customer_id\n"
                )
            },
        ),
        failure_case(
            name="invalid-declaration-name",
            expected_code="D016",
            files={
                "models/staging/_sqlbuild/_constants/limits.sql": (
                    "CONSTANT (name MinimumAmount, value 1);\n"
                ),
                **staging_files(FAILURE_BASE_STAGING + 'WHERE amount > @const("MinimumAmount")\n'),
            },
        ),
        failure_case(
            name="python-node-syntax",
            expected_code="D011",
            files={"python/tasks/exports.py": "def broken(:\n    pass\n"},
        ),
        failure_case(
            name="hook-unknown-argument",
            expected_code="P001",
            files={
                "hooks/sql/record_refresh.sql": (
                    "HOOK (\n  description \"Record a refresh\"\n);\n\nSELECT @'label' AS label\n"
                ),
                FAILURE_MART_PATH: FAILURE_BASE_MART.replace(
                    '"Order totals per customer",',
                    '"Order totals per customer",\n  post_hooks [sql("record_refresh", tag: "x")],',
                ),
            },
        ),
        failure_case(
            name="model-private-enum-misuse",
            expected_code="P001",
            files=staging_files(
                'MODEL (\n  description "Staged orders",\n'
                "  enums (\n    _state [OPEN, CLOSED],\n  ),\n);\n\n"
                "SELECT order_id, customer_id, amount, status\n"
                'FROM __source("raw_orders")\nWHERE status = @enum("_state").PENDING\n'
            ),
        ),
        failure_case(
            name="variable-not-defined",
            expected_code="P001",
            files=staging_files(
                FAILURE_BASE_STAGING.replace("status\n", "status, '@@region' AS region\n", 1)
            ),
        ),
    )
