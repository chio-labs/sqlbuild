"""Every Rule fact reads the same values from the trimmed host payload as from the full project."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.rule_engine._helpers.engine.custom_rules import host_project
from sqlbuild.rule_engine._helpers.host.custom_host_pool import host_payload_project
from sqlbuild.rule_engine.classes.project_tree import public_model
from sqlbuild.rule_engine.types import FactKey
from tests.integration.src.sqlbuild.rule_engine.host_payload._test_types import (
    HostPayloadFactsTestCase,
)
from tests.integration.src.sqlbuild.rule_engine.host_payload.helpers import (
    compile_files,
    dropped_fields,
    fact_digests,
    record_trimmed_fields,
)


@pytest.mark.parametrize(
    "test_case",
    (
        HostPayloadFactsTestCase(
            description="sources, refs, contracts, macros, declarations, tests, and audits",
            project_files={
                "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_orders\n    description: Raw orders.\n"
                    '    expression: "(SELECT 1 AS id, CAST(10.5 AS DOUBLE) AS amount)"\n'
                    "    columns:\n      - name: id\n        type: INTEGER\n"
                    "  - name: raw_customers\n    description: Raw customers.\n"
                    '    expression: "(SELECT 1 AS customer_id)"\n'
                ),
                "constants/policy.sql": "CONSTANT (name minimum_amount, value 7);\n",
                "enums/order_status.sql": "ENUM (name order_status, members [PAID, OPEN]);\n",
                "models/marts/_sqlbuild/_macros/amounts.py": (
                    'def doubled(amount: str) -> str:\n    return f"({amount}) * 2"\n'
                ),
                "models/staging/stg_orders.sql": (
                    "MODEL (description 'Staged orders.',\n  contract enforced,\n"
                    "  columns (\n"
                    "    order_id (type INTEGER, nullable false, audits [not_null]),\n"
                    "    amount (type DOUBLE),\n    status (type order_status),\n  ),\n);\n\n"
                    "SELECT CAST(id AS INTEGER) AS order_id, amount, 'PAID' AS status\n"
                    'FROM __source("raw_orders")\n'
                ),
                "models/marts/order_totals.sql": (
                    'MODEL (description "Order totals", materialized table);\n\n'
                    'SELECT o.order_id, @doubled("o.amount") AS doubled_amount, o.status\n'
                    'FROM __ref("stg_orders") AS o WHERE o.amount > 7\n'
                ),
                "models/marts/order_flags.sql": (
                    'MODEL (description "Order flags");\n\n'
                    'SELECT o.order_id, o.missing_flag AS flag FROM __ref("stg_orders") AS o\n'
                ),
                "models/marts/flag_counts.sql": (
                    'MODEL (description "Flag counts");\n\n'
                    'SELECT f.flag FROM __ref("order_flags") AS f\n'
                ),
                "hooks/sql/analyze_orders.sql": (
                    'HOOK (description "Analyze orders");\n\nSELECT 1\n'
                ),
                "hooks/python/order_hooks.py": (
                    "from sqlbuild.hooks import hook\n\n"
                    "@hook\n"
                    "def log_orders(ctx):\n"
                    "    '''Log orders.'''\n"
                    "    ctx.execute_sql('INSERT INTO audit_log SELECT 1')\n"
                ),
                "python/loaders/order_rows.py": (
                    "from sqlbuild.loaders import loader\n\n"
                    "@loader(columns=[{'name': 'order_id', 'type': 'INTEGER'}])\n"
                    "def fetch_orders(ctx):\n"
                    "    '''Fetch orders.'''\n"
                    "    return [{'order_id': 1}]\n"
                ),
                "materializations/copy_table.py": (
                    "from sqlbuild.executor.custom.models import (\n"
                    "    MaterializationContext,\n    MaterializationResult,\n)\n\n\n"
                    "def materialize(ctx: MaterializationContext) -> MaterializationResult:\n"
                    '    ctx.execute_sql(f"CREATE TABLE {ctx.destination} AS {ctx.sql}")\n'
                    "    return MaterializationResult(relation=ctx.destination)\n"
                ),
                "tests/scenarios/paid_orders.sql": (
                    "SCENARIO (description 'Paid orders.');\n\n"
                    "WITH\n__source__raw_orders AS (SELECT 1 AS id, 10.5 AS amount),\n"
                    "__expected__stg_orders AS (\n"
                    "  SELECT 1 AS order_id, 10.5 AS amount, 'PAID' AS status\n)\n"
                    "SELECT 1\n"
                ),
                "tests/unit/test_order_totals.sql": (
                    "TEST ();\n\nWITH\n__ref__stg_orders AS (\n"
                    "  SELECT 1 AS order_id, 10.0 AS amount\n),\n"
                    "__expected__order_totals AS (\n"
                    "  SELECT 1 AS order_id, 20.0 AS doubled_amount, 'PAID' AS status\n)\n"
                    "SELECT 1\n"
                ),
            },
            expected_unpopulated_trimmed_fields=frozenset({"native_session"}),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_trimming_host_payload_then_every_fact_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: HostPayloadFactsTestCase
) -> None:
    project: CompiledProject = compile_files(root=tmp_path, files=test_case.project_files)
    trimmed_fields: dict[type[object], set[str]] = record_trimmed_fields(monkeypatch)
    trimmed: CompiledProject = host_payload_project(host_project(project))

    full_digests: dict[FactKey, tuple[str, str]] = fact_digests(project=project, root=tmp_path)
    trimmed_digests: dict[FactKey, tuple[str, str]] = fact_digests(project=trimmed, root=tmp_path)

    assert trimmed_digests == full_digests
    assert tuple(map(public_model, trimmed.models)) == tuple(map(public_model, project.models))
    assert (
        dropped_fields(before=project, after=trimmed)
        == trimmed_fields[CompiledProject] - test_case.expected_unpopulated_trimmed_fields
    )
    assert (
        frozenset().union(
            *(
                dropped_fields(before=model, after=trimmed_model)
                for model, trimmed_model in zip(project.models, trimmed.models, strict=True)
            )
        )
        == trimmed_fields[CompiledModel] - test_case.expected_unpopulated_trimmed_fields
    )
