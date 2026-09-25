"""Canonical formatting retains authored syntax and compiler-scale query budgets."""

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import FormatterSyntaxTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        FormatterSyntaxTestCase(
            "casts and qualified aliases",
            "SELECT CAST(o.amount AS NUMERIC(10, 2)) AS amount, o.amount::DOUBLE AS total FROM orders o",
            ("CAST(o.amount AS NUMERIC(10, 2))", "o.amount::DOUBLE"),
        ),
        FormatterSyntaxTestCase(
            "variant paths and keyword keys",
            "SELECT o.payload:customer.name::VARCHAR AS customer_name, o.payload:index::INTEGER AS item_index FROM orders o",
            ("o.payload:customer.name::VARCHAR", "o.payload:index::INTEGER"),
        ),
        FormatterSyntaxTestCase(
            "literal spelling",
            r"SELECT $$Order summary$$ AS label, 'Customer''s order' AS other_label, '\\s+' AS pattern, 1.25e-5 AS ratio, TIMESTAMP '2025-01-01 00:00:00' AS created_at",
            (
                "$$Order summary$$",
                "'Customer''s order'",
                r"'\\s+'",
                "1.25e-5",
                "TIMESTAMP '2025-01-01 00:00:00'",
            ),
        ),
        FormatterSyntaxTestCase(
            "null treatment and function syntax",
            "SELECT FIRST_VALUE(o.id IGNORE NULLS) OVER (ORDER BY o.id) AS first_id, POSITION('new' IN o.status) AS status_position, MOD(o.id, 2) AS remainder FROM orders o",
            ("FIRST_VALUE(o.id IGNORE NULLS)", "POSITION('new' IN o.status)", "MOD(o.id, 2)"),
        ),
        FormatterSyntaxTestCase(
            "typed lambda",
            "SELECT TRANSFORM(o.items, item VARIANT -> item:order_id::INTEGER) AS order_ids FROM orders o",
            ("item VARIANT ->", "item:order_id::INTEGER"),
        ),
        FormatterSyntaxTestCase(
            "commented cast parameters",
            "SELECT CAST(amount AS NUMERIC(/* precision */ 10, 2)) AS amount FROM orders",
            ("/* precision */", "NUMERIC("),
        ),
        FormatterSyntaxTestCase(
            "trailing projection comma",
            "SELECT o.order_id, -- Keep the order identifier.\nFROM orders o",
            ("-- Keep the order identifier.", "o.order_id"),
        ),
        FormatterSyntaxTestCase(
            "compiler function depth",
            "SELECT " + "LOWER(" * 80 + "'NEW'" + ")" * 80 + " AS status",
            ("'NEW'", "AS status"),
        ),
        FormatterSyntaxTestCase(
            "compiler set operation budget",
            " UNION ALL ".join("SELECT 1 AS order_id" for _ in range(300)),
            ("UNION ALL", "AS order_id"),
        ),
        FormatterSyntaxTestCase(
            "CTE-producing macro",
            "WITH @order_input(), final AS (SELECT order_id FROM orders) SELECT * FROM final",
            ("@order_input()", "final AS ("),
            'def order_input() -> str:\n    """Return an orders input CTE."""\n'
            '    return "orders AS (SELECT 1 AS order_id)"\n',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_syntax_when_formatting_then_spelling_and_idempotence_are_preserved(
    test_case: FormatterSyntaxTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "snowflake"\n')
    macros: Path = tmp_path / "models" / "_macros"
    macros.mkdir(parents=True)
    (macros / "orders.py").write_text(test_case.macro_source)
    model: Path = tmp_path / "models" / "order_summary.sql"
    model.write_text(
        'MODEL (description "Order summary", database warehouse, schema analytics);\n-- Order query.\n'
        + test_case.sql
        + "\n"
    )
    assert main(["--project-dir", str(tmp_path), "format", "--json"]) == 0
    capsys.readouterr()
    formatted: str = model.read_text()
    assert all(fragment in formatted for fragment in test_case.expected_fragments)
    assert main(["--project-dir", str(tmp_path), "format", "--check", "--json"]) == 0
    assert model.read_text() == formatted
    assert main(["--project-dir", str(tmp_path), "compile", "--no-cache"]) == 0


@pytest.mark.parametrize(
    "test_case",
    [
        FormatterSyntaxTestCase(
            "computed variant key needs source-preserving parser support",
            "SELECT payload:customers[TO_VARCHAR(order_id)] AS customer FROM orders",
            ("format-unsafe", "Expected RBracket"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_variant_key_when_formatting_then_compilable_file_stays_untouched(
    test_case: FormatterSyntaxTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "snowflake"\n')
    model: Path = tmp_path / "models" / "order_summary.sql"
    model.parent.mkdir()
    original: str = (
        'MODEL (description "Order summary", database warehouse, schema analytics);   \n'
        + test_case.sql
        + "\n"
    )
    model.write_text(original)
    assert main(["--project-dir", str(tmp_path), "compile", "--no-cache"]) == 0
    capsys.readouterr()
    assert main(["--project-dir", str(tmp_path), "format", "--json"]) == 1
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert all(fragment in json.dumps(payload) for fragment in test_case.expected_fragments)
    assert payload["formatted_files"] == []
    assert model.read_text() == original
    assert main(["--project-dir", str(tmp_path), "format", "--check", "--json"]) == 1
    assert model.read_text() == original


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
