"""Attached audits that read other resources gate their target and cannot read its dependants."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    AttachedAuditGateCycleTestCase,
    AttachedAuditGateTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    compile_and_assemble,
    execution_edge_names,
    gate_audit,
    gate_model,
)

_PROJECT_FILE: str = """
name = "demo"
adapter = "duckdb"

[settings]
sql_analysis = false
sql_validation = false
"""
_SOURCES_WITH_AUDIT: str = (
    "sources:\n  - name: raw_orders\n    table: orders\n    audits:\n      - code_check\n"
)
_SEED_WITH_AUDIT: str = (
    "seeds:\n  - name: order_codes\n    columns:\n      - name: code\n        type: VARCHAR\n"
    "    audits:\n      - code_check\n"
)
_AUDITED_HEADER: str = "MODEL (audits [code_check]);"
_ALLOWED_SEED: str = (
    "seeds:\n  - name: allowed_codes\n    columns:\n      - name: code\n        type: VARCHAR\n"
)


@pytest.mark.parametrize(
    "test_case",
    (
        AttachedAuditGateTestCase(
            "model audit reading a sibling model makes the model wait for it",
            {
                "audits/generic/code_check.sql": gate_audit(read='__ref("allowed")'),
                "models/allowed.sql": gate_model(sql="SELECT 'A' AS code"),
                "models/orders.sql": gate_model(sql="SELECT 'A' AS code", header=_AUDITED_HEADER),
            },
            (("orders", "allowed"),),
        ),
        AttachedAuditGateTestCase(
            "source audit reading an unrelated model makes the source's dependants wait",
            {
                "audits/generic/code_check.sql": gate_audit(read='__ref("allowed")'),
                "sources/raw.yml": _SOURCES_WITH_AUDIT,
                "models/allowed.sql": gate_model(sql="SELECT 'A' AS code"),
                "models/staged_orders.sql": gate_model(sql='SELECT * FROM __source("raw_orders")'),
                "models/other_orders.sql": gate_model(sql='SELECT * FROM __source("raw_orders")'),
            },
            (("other_orders", "allowed"), ("staged_orders", "allowed")),
        ),
        AttachedAuditGateTestCase(
            "seed audit reading another seed makes the seed wait for it",
            {
                "audits/generic/code_check.sql": gate_audit(read='__seed("allowed_codes")'),
                "seeds/order_codes.yml": _SEED_WITH_AUDIT,
                "seeds/order_codes.csv": "code\nA\n",
                "seeds/allowed_codes.yml": _ALLOWED_SEED,
                "seeds/allowed_codes.csv": "code\nA\n",
            },
            (("order_codes", "allowed_codes"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_attached_audit_reading_another_resource_when_compiling_then_it_adds_ordering_edges(
    test_case: AttachedAuditGateTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    project: CompiledProject = compile_and_assemble(project_dir=tmp_path)

    assert set(test_case.expected_edges) <= execution_edge_names(project=project)


@pytest.mark.parametrize(
    "test_case",
    (
        AttachedAuditGateCycleTestCase(
            "model audit reading a model built from its target",
            {
                "audits/generic/code_check.sql": gate_audit(read='__ref("orders_mart")'),
                "models/orders.sql": gate_model(sql="SELECT 'A' AS code", header=_AUDITED_HEADER),
                "models/orders_mart.sql": gate_model(sql='SELECT * FROM __ref("orders")'),
            },
            (
                "[P005]",
                "Audit 'code_check' on model 'orders' reads model 'orders_mart'",
                "singular audit",
            ),
        ),
        AttachedAuditGateCycleTestCase(
            "source audit reading a model built from the source",
            {
                "audits/generic/code_check.sql": gate_audit(read='__ref("staged_orders")'),
                "sources/raw.yml": _SOURCES_WITH_AUDIT,
                "models/staged_orders.sql": gate_model(sql='SELECT * FROM __source("raw_orders")'),
            },
            (
                "[P005]",
                "on source 'raw_orders' reads model 'staged_orders'",
                "singular audit",
            ),
        ),
        AttachedAuditGateCycleTestCase(
            "seed audit reading a model built from the seed",
            {
                "audits/generic/code_check.sql": gate_audit(read='__ref("coded_orders")'),
                "seeds/order_codes.yml": _SEED_WITH_AUDIT,
                "seeds/order_codes.csv": "code\nA\n",
                "models/coded_orders.sql": gate_model(sql='SELECT * FROM __seed("order_codes")'),
            },
            (
                "[P005]",
                "on seed 'order_codes' reads model 'coded_orders'",
                "singular audit",
            ),
        ),
        AttachedAuditGateCycleTestCase(
            "two model audits that each read the other's target",
            {
                "audits/generic/code_check.sql": gate_audit(read='__ref("customers")'),
                "audits/generic/order_check.sql": gate_audit(read='__ref("orders")'),
                "models/orders.sql": gate_model(sql="SELECT 'A' AS code", header=_AUDITED_HEADER),
                "models/customers.sql": "MODEL (audits [order_check]);\nSELECT 'A' AS code",
            },
            ("[P005]", "which depends on"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_attached_audit_reading_its_targets_dependant_when_compiling_then_it_fails(
    test_case: AttachedAuditGateCycleTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, {"sqlbuild_project.toml": _PROJECT_FILE} | test_case.files)

    with pytest.raises(ValueError) as error:
        compile_and_assemble(project_dir=tmp_path)

    rendered: str = (
        f"[{getattr(error.value, 'code', '')}] {error.value} {getattr(error.value, 'help', '')}"
    )
    for fragment in test_case.expected_error_fragments:
        assert fragment in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
