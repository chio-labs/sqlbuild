"""Tests for model and column reference rewriting in YAML and declaration headers."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.refactoring._helpers.text.header_edits import (
    consumer_column_header_edits,
    model_name_header_edits,
)
from sqlbuild.compiler.refactoring._helpers.text.schema_edits import (
    schema_column_edits,
    schema_model_name_edits,
)
from sqlbuild.compiler.refactoring._helpers.text.text_edits import apply_text_edits
from sqlbuild.compiler.refactoring._helpers.text.yaml_edits import (
    yaml_column_edits,
    yaml_model_edits,
)
from sqlbuild.compiler.refactoring.models import TextEdit
from tests.unit.src.sqlbuild.compiler.refactoring._helpers._test_types import (
    DeclarationEditTestCase,
)
from tests.unit.src.sqlbuild.compiler.refactoring._helpers.helpers import yaml_file

_BODY: str = "SELECT order_id FROM orders\n"


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationEditTestCase(
            description="relationships target written as a reference",
            contents=(
                "seeds:\n  - name: customers\n    columns:\n      - name: customer_id\n"
                "        audits:\n          - relationships:\n"
                '              to: __ref("fact_orders")\n              field: customer_id\n'
            ),
            expected_contents=(
                "seeds:\n  - name: customers\n    columns:\n      - name: customer_id\n"
                "        audits:\n          - relationships:\n"
                '              to: __ref("order_facts")\n              field: customer_id\n'
            ),
        ),
        DeclarationEditTestCase(
            description="bare relationships target in a flow mapping",
            contents="audits:\n  - relationships: {to: fact_orders, field: customer_id}\n",
            expected_contents="audits:\n  - relationships: {to: order_facts, field: customer_id}\n",
        ),
        DeclarationEditTestCase(
            description="reference inside an escaped double-quoted expression",
            contents='audits:\n  - expression_is_true: {expression: "id IN (SELECT id FROM '
            '__ref(\\"fact_orders\\"))"}\n',
            expected_contents='audits:\n  - expression_is_true: {expression: "id IN (SELECT id '
            'FROM __ref(\\"order_facts\\"))"}\n',
        ),
        DeclarationEditTestCase(
            description="similar names and descriptions are left alone",
            contents=(
                "sources:\n  - name: raw\n    description: fact_orders feed\n"
                "    audits:\n      - relationships: {to: fact_orders_daily, field: id}\n"
            ),
            expected_contents=(
                "sources:\n  - name: raw\n    description: fact_orders feed\n"
                "    audits:\n      - relationships: {to: fact_orders_daily, field: id}\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_yaml_when_renaming_model_then_references_follow(
    test_case: DeclarationEditTestCase,
) -> None:
    edits: tuple[tuple[str, TextEdit], ...] = yaml_model_edits(
        files=(yaml_file(test_case.contents),), old="fact_orders", new="order_facts"
    )

    assert (
        apply_text_edits(text=test_case.contents, edits=tuple(edit for _, edit in edits))
        == test_case.expected_contents
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationEditTestCase(
            description="field of a relationship to the model",
            contents="audits:\n  - relationships: {to: '__ref(\"fact_orders\")', field: amount}\n",
            expected_contents=(
                "audits:\n  - relationships: {to: '__ref(\"fact_orders\")', field: revenue}\n"
            ),
        ),
        DeclarationEditTestCase(
            description="field of a relationship to another model",
            contents="audits:\n  - relationships: {to: '__ref(\"customers\")', field: amount}\n",
            expected_contents=(
                "audits:\n  - relationships: {to: '__ref(\"customers\")', field: amount}\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_yaml_when_renaming_column_then_relationship_fields_follow(
    test_case: DeclarationEditTestCase,
) -> None:
    edits: tuple[tuple[str, TextEdit], ...] = yaml_column_edits(
        files=(yaml_file(test_case.contents),), model="fact_orders", old="amount", new="revenue"
    )

    assert (
        apply_text_edits(text=test_case.contents, edits=tuple(edit for _, edit in edits))
        == test_case.expected_contents
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationEditTestCase(
            description="MODEL header quoted SQL and bare relationships target",
            contents=(
                'MODEL (\n  audits [expression_is_true (expression "id IN (SELECT id FROM '
                "__ref('fact_orders'))\")],\n  columns (\n    id (audits [relationships "
                f"(to fact_orders, field id)]),\n  ),\n);\n{_BODY}"
            ),
            expected_contents=(
                'MODEL (\n  audits [expression_is_true (expression "id IN (SELECT id FROM '
                "__ref('order_facts'))\")],\n  columns (\n    id (audits [relationships "
                f"(to order_facts, field id)]),\n  ),\n);\n{_BODY}"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_header_when_renaming_model_then_quoted_and_bare_references_follow(
    test_case: DeclarationEditTestCase,
) -> None:
    edits: tuple[TextEdit, ...] = model_name_header_edits(
        contents=test_case.contents, old="fact_orders", new="order_facts"
    )

    assert apply_text_edits(text=test_case.contents, edits=edits) == test_case.expected_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationEditTestCase(
            description="field of a referenced relationship target",
            contents=(
                "MODEL (\n  columns (\n    id (audits [relationships "
                f'(to __ref("fact_orders"), field amount)]),\n  ),\n);\n{_BODY}'
            ),
            expected_contents=(
                "MODEL (\n  columns (\n    id (audits [relationships "
                f'(to __ref("fact_orders"), field revenue)]),\n  ),\n);\n{_BODY}'
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_header_when_renaming_column_then_relationship_fields_follow(
    test_case: DeclarationEditTestCase,
) -> None:
    edits: tuple[TextEdit, ...] = consumer_column_header_edits(
        contents=test_case.contents, upstream="fact_orders", old="amount", new="revenue"
    )

    assert apply_text_edits(text=test_case.contents, edits=edits) == test_case.expected_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationEditTestCase(
            description="bare target and quoted SQL in every SCHEMA of a file",
            contents=(
                "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships "
                "(to fact_orders, field id)]),\n  ),\n);\n\n"
                "SCHEMA (\n  name order_totals,\n  audits [expression_is_true (expression "
                "\"total > (SELECT 0 FROM __ref('fact_orders') LIMIT 1)\")],\n);\n"
            ),
            expected_contents=(
                "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships "
                "(to order_facts, field id)]),\n  ),\n);\n\n"
                "SCHEMA (\n  name order_totals,\n  audits [expression_is_true (expression "
                "\"total > (SELECT 0 FROM __ref('order_facts') LIMIT 1)\")],\n);\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_file_when_renaming_model_then_references_follow(
    test_case: DeclarationEditTestCase,
) -> None:
    edits: tuple[TextEdit, ...] = schema_model_name_edits(
        contents=test_case.contents, old="fact_orders", new="order_facts"
    )

    assert apply_text_edits(text=test_case.contents, edits=edits) == test_case.expected_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationEditTestCase(
            description="field of a relationship to the model",
            contents=(
                "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships "
                '(to __ref("fact_orders"), field amount)]),\n  ),\n);\n'
            ),
            expected_contents=(
                "SCHEMA (\n  name order_shape,\n  columns (\n    id (audits [relationships "
                '(to __ref("fact_orders"), field revenue)]),\n  ),\n);\n'
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_file_when_renaming_column_then_relationship_fields_follow(
    test_case: DeclarationEditTestCase,
) -> None:
    edits: tuple[TextEdit, ...] = schema_column_edits(
        contents=test_case.contents, upstream="fact_orders", old="amount", new="revenue"
    )

    assert apply_text_edits(text=test_case.contents, edits=edits) == test_case.expected_contents


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
