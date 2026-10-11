"""Audits attached by the native model loop and assembled into the native compiled project."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import AuditInput, CompiledAuditView
from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    NativeAuditAttachmentTestCase,
    NativeAuditErrorTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    AUDIT_PROJECT_FILES,
    audit_summary,
    compile_function_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeAuditAttachmentTestCase(
            description="singular audit reading two models under its own run scope",
            audit_name="orders_have_customers",
            expected_summary=(
                "NativeCompiledAudit",
                "orders_have_customers",
                ("orders", "customers"),
                "warn",
                "final",
                (None, None),
                'SELECT * FROM __ref("orders") o LEFT JOIN __ref("customers") c'
                " ON o.order_id = c.customer_id WHERE c.customer_id IS NULL",
            ),
            expected_usages=(
                "singular_audit:orders_have_customers:customers",
                "singular_audit:orders_have_customers:orders",
            ),
        ),
        NativeAuditAttachmentTestCase(
            description="built-in column audit under the project default severity",
            audit_name="not_null",
            expected_summary=(
                "NativeCompiledAudit",
                "not_null",
                ("orders",),
                "warn",
                "delta_and_final",
                ("orders", "order_id"),
                'SELECT order_id\nFROM __ref("orders")\nWHERE order_id IS NULL',
            ),
            expected_usages=(),
        ),
        NativeAuditAttachmentTestCase(
            description="project generic audit with an argument and its own severity",
            audit_name="at_least",
            expected_summary=(
                "NativeCompiledAudit",
                "at_least",
                ("orders",),
                "error",
                "delta_and_final",
                ("orders", "order_id"),
                'SELECT * FROM __ref("orders") WHERE order_id < 1',
            ),
            expected_usages=("audit:at_least:orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_when_compiling_then_native_project_holds_its_attachment(
    test_case: NativeAuditAttachmentTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, inputs = compile_function_project(
        project_dir=tmp_path, files=AUDIT_PROJECT_FILES, monkeypatch=monkeypatch
    )

    audits: dict[str, CompiledAuditView] = {audit.name: audit for audit in project.audits}
    audit_inputs: dict[str, AuditInput] = {
        audit.definition_name: audit_input
        for audit, audit_input in zip(project.audits, inputs.audit_inputs, strict=True)
    }
    assert audit_summary(audits[test_case.audit_name]) == test_case.expected_summary
    assert (
        tuple(
            f"{usage.declaration.kind.value}:{usage.declaration.name}:{usage.consumer.name}"
            for usage in audit_inputs[test_case.audit_name].declaration_usages
        )
        == test_case.expected_usages
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NativeAuditErrorTestCase(
            description="attachment of an unknown generic audit",
            files={
                "models/customers.sql": (
                    "MODEL (description 'Customers.', columns (customer_id (type INTEGER,"
                    " audits [at_most(maximum 3)])));\nSELECT 1 AS customer_id\n"
                ),
            },
            expected_message="references unknown generic audit 'at_most'",
        ),
        NativeAuditErrorTestCase(
            description="singular audit reading an unknown model",
            files={
                "audits/singular/orders_have_customers.sql": (
                    "AUDIT (name orders_have_customers);\n"
                    'SELECT * FROM __ref("orders") JOIN __ref("missing_customers") ON TRUE\n'
                ),
            },
            expected_message=(
                "Audit file audits/singular/orders_have_customers.sql references unknown model"
                " 'missing_customers'"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_audit_when_compiling_then_native_attachment_rejects_it(
    test_case: NativeAuditErrorTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(CompileInputError) as raised:
        _ = compile_function_project(
            project_dir=tmp_path,
            files={**AUDIT_PROJECT_FILES, **test_case.files},
            monkeypatch=monkeypatch,
        )

    assert test_case.expected_message in str(raised.value)
