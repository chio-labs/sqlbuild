"""Tests for token-exact MODEL header edits."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.refactoring._helpers.header_edits import (
    insert_header_entry_edit,
    model_name_header_edits,
)
from sqlbuild.compiler.refactoring._helpers.text_edits import apply_text_edits
from sqlbuild.compiler.refactoring.models import TextEdit
from tests.unit.src.sqlbuild.compiler.refactoring._helpers._test_types import HeaderEditTestCase
from tests.unit.src.sqlbuild.compiler.refactoring._helpers.helpers import migrated_column_edits

_BODY: str = "SELECT order_id, amount FROM orders\n"


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderEditTestCase(
            description="declared column gains migrate_from before its metadata",
            contents=f"MODEL (\n  columns (\n    amount (nullable false),\n  ),\n);\n{_BODY}",
            expected_contents=(
                "MODEL (\n  columns (\n    revenue (migrate_from amount, nullable false),\n"
                f"  ),\n);\n{_BODY}"
            ),
        ),
        HeaderEditTestCase(
            description="bare declared column gains a migrate_from block",
            contents=f"MODEL (\n  columns (amount),\n);\n{_BODY}",
            expected_contents=f"MODEL (\n  columns (revenue (migrate_from amount)),\n);\n{_BODY}",
        ),
        HeaderEditTestCase(
            description="undeclared column gets a new columns entry",
            contents=f"MODEL (\n  materialized incremental,\n);\n{_BODY}",
            expected_contents=(
                "MODEL (\n  columns (revenue (migrate_from amount)),\n"
                f"  materialized incremental,\n);\n{_BODY}"
            ),
        ),
        HeaderEditTestCase(
            description="column-valued config follows the column",
            contents=f"MODEL (\n  unique_key [order_id, amount],\n);\n{_BODY}",
            expected_contents=(
                "MODEL (\n  columns (revenue (migrate_from amount)),\n"
                f"  unique_key [order_id, revenue],\n);\n{_BODY}"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_header_when_renaming_migrated_column_then_header_is_rewritten(
    test_case: HeaderEditTestCase,
) -> None:
    edits: tuple[TextEdit, ...] = migrated_column_edits(test_case.contents)

    assert apply_text_edits(text=test_case.contents, edits=edits) == test_case.expected_contents


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderEditTestCase(
            description="cursor_inputs keys and relationships targets follow the model",
            contents=(
                "MODEL (\n  cursor_inputs (\n    fact_orders ordered_at,\n  ),\n"
                "  columns (\n    order_id (audits [relationships (to fact_orders, "
                "field order_id)]),\n  ),\n);\n"
                f"{_BODY}"
            ),
            expected_contents=(
                "MODEL (\n  cursor_inputs (\n    order_facts ordered_at,\n  ),\n"
                "  columns (\n    order_id (audits [relationships (to order_facts, "
                "field order_id)]),\n  ),\n);\n"
                f"{_BODY}"
            ),
        ),
        HeaderEditTestCase(
            description="descriptions naming the model are left alone",
            contents=f'MODEL (\n  description "fact_orders summary",\n);\n{_BODY}',
            expected_contents=f'MODEL (\n  description "fact_orders summary",\n);\n{_BODY}',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_header_when_renaming_model_then_references_follow(
    test_case: HeaderEditTestCase,
) -> None:
    edits: tuple[TextEdit, ...] = model_name_header_edits(
        contents=test_case.contents, old="fact_orders", new="order_facts"
    )

    assert apply_text_edits(text=test_case.contents, edits=edits) == test_case.expected_contents


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderEditTestCase(
            description="multi-line header gets its own line",
            contents=f"MODEL (\n  materialized table,\n);\n{_BODY}",
            expected_contents=(
                f"MODEL (\n  migrate_from fact_orders,\n  materialized table,\n);\n{_BODY}"
            ),
        ),
        HeaderEditTestCase(
            description="empty header is expanded",
            contents=f"MODEL ();\n{_BODY}",
            expected_contents=f"MODEL (\n  migrate_from fact_orders,\n);\n{_BODY}",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_header_when_adding_model_migration_then_entry_is_inserted(
    test_case: HeaderEditTestCase,
) -> None:
    edit: TextEdit | None = insert_header_entry_edit(
        contents=test_case.contents,
        entry="migrate_from fact_orders",
        display="migrate_from fact_orders",
    )

    assert edit is not None
    assert apply_text_edits(text=test_case.contents, edits=(edit,)) == test_case.expected_contents


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
