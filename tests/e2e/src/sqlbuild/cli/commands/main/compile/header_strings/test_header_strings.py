"""E2E coverage of header string quoting and folded descriptions through the real CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.header_strings._test_types import (
    FoldedDescriptionTestCase,
    HeaderQuoteErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.header_strings.helpers import (
    header_strings_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_QUOTE_MESSAGE: str = (
    'a double quote ends this "..." string early; use """…""" for text containing double quotes'
)

_TITLE_MACRO: str = (
    "MACRO (\n"
    '  description """\n'
    "    True when a title is a woman's title, with or without a dot\n"
    '    ("Miss", "Mrs. C. O\'Brien").\n'
    '  """,\n'
    "  arguments (title VARCHAR),\n"
    "  returns BOOLEAN,\n"
    ");\n\n"
    "LOWER(@title) IN ('miss', 'mrs', 'ms')\n"
)

_CUSTOMER_SCHEMA: str = (
    "SCHEMA (\n"
    "  name customer,\n"
    '  description """One customer, as "the shop" knows them."""\n'
    "  ,\n"
    "  columns (\n"
    "    customer_id (type BIGINT, description \"The customer's\n"
    '      key.")\n'
    "  ),\n"
    ");\n"
)

_CUSTOMERS_MODEL: str = (
    "MODEL (\n"
    '  description """\n'
    '    Customers with a "woman\'s title" flag,\n'
    "    one row each.\n"
    "\n"
    "    Built from the raw seed.\n"
    '  """,\n'
    "  model_schema customer,\n"
    "  columns (\n"
    '    is_womans_title (type BOOLEAN, description "True for Miss,\n'
    '      Mrs and Ms.")\n'
    "  ),\n"
    ");\n\n"
    "SELECT customer_id, @sql.is_womans_title(title) AS is_womans_title\n"
    'FROM __seed("raw_customers")\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderQuoteErrorTestCase(
            description="model_description_escaping_a_quote",
            path="models/customers.sql",
            contents=(
                'MODEL (\n  description "Matches a title (\\"Miss\\").",\n);\n\n'
                "SELECT 1 AS customer_id\n"
            ),
            expected_code="D002",
            expected_location="models/customers.sql:2:34",
            expected_message=_QUOTE_MESSAGE,
        ),
        HeaderQuoteErrorTestCase(
            description="macro_description_escaping_a_quote",
            path="macros/sql/title.sql",
            contents=(
                'MACRO (\n  description "Matches a title (\\"Miss\\").",\n'
                "  arguments (value VARCHAR),\n  returns VARCHAR,\n);\n\n@value\n"
            ),
            expected_code="P015",
            expected_location="macros/sql/title.sql:2:34",
            expected_message=_QUOTE_MESSAGE,
        ),
        HeaderQuoteErrorTestCase(
            description="wrapped_macro_description_with_apostrophes_escaping_quotes",
            path="macros/sql/title.sql",
            contents=(
                "MACRO (\n"
                "  description \"True when a name starts with a woman's title: Mme, Mlle, Miss, "
                "Mrs, Ms. Any case,\n"
                'with or without a dot (\\"MISS ANNA PARKER\\", \\"Mrs. C. O\'Brien\\", '
                '\\"Ms.Robinson\\"). Capital\n'
                'initials before a surname (\\"MS. Ramos\\" for M. S. Ramos) are not a title.",\n'
                "  arguments (value VARCHAR),\n  returns VARCHAR,\n);\n\n@value\n"
            ),
            expected_code="P015",
            expected_location="macros/sql/title.sql:3:25",
            expected_message=_QUOTE_MESSAGE,
        ),
        HeaderQuoteErrorTestCase(
            description="schema_description_escaping_a_quote",
            path="schemas/customer.sql",
            contents=(
                'SCHEMA (\n  name customer,\n  description "The \\"shop\\" customer",\n'
                "  columns (customer_id (type BIGINT)),\n);\n"
            ),
            expected_code="D013",
            expected_location="schemas/customer.sql:3:21",
            expected_message=_QUOTE_MESSAGE,
        ),
        HeaderQuoteErrorTestCase(
            description="unclosed_triple_quote",
            path="models/customers.sql",
            contents=(
                'MODEL (\n  description """Never closed,\n  materialized table,\n);\n\n'
                "SELECT 1 AS customer_id\n"
            ),
            expected_code="D002",
            expected_location="models/customers.sql:2:15",
            expected_message='this """ string is never closed',
        ),
        HeaderQuoteErrorTestCase(
            description="triple_quote_inside_a_triple_quoted_string",
            path="models/customers.sql",
            contents=(
                'MODEL (\n  description """He said """hi""" twice.""",\n);\n\n'
                "SELECT 1 AS customer_id\n"
            ),
            expected_code="D002",
            expected_location="models/customers.sql:2:26",
            expected_message='""" inside a """...""" string ends it early',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_misquoted_header_string_when_compiling_then_error_names_the_quote_and_the_fix(
    test_case: HeaderQuoteErrorTestCase, tmp_path: Path
) -> None:
    project_dir: Path = header_strings_project(tmp_path, {test_case.path: test_case.contents})

    result: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "compile")
    )

    output: str = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert test_case.expected_message in output, output
    assert test_case.expected_location in output, output
    assert test_case.expected_code in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        FoldedDescriptionTestCase(
            description="triple_quoted_and_wrapped_model_schema_and_macro_descriptions",
            files={
                "macros/sql/is_womans_title.sql": _TITLE_MACRO,
                "schemas/customer.sql": _CUSTOMER_SCHEMA,
                "models/customers.sql": _CUSTOMERS_MODEL,
            },
            expected_description=(
                'Customers with a "woman\'s title" flag, one row each.\n\nBuilt from the raw seed.'
            ),
            expected_column_descriptions={
                "is_womans_title": "True for Miss, Mrs and Ms.",
                "customer_id": "The customer's key.",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_triple_quoted_and_wrapped_descriptions_when_compiling_then_folded_text_is_stored(
    test_case: FoldedDescriptionTestCase, tmp_path: Path
) -> None:
    project_dir: Path = header_strings_project(tmp_path, test_case.files)

    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "compile", "--manifest")
    )
    dag: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "dag", "--json")
    )

    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    assert dag.returncode == 0, dag.stderr
    manifest: dict[str, Any] = json.loads((project_dir / "target/manifest.json").read_text())
    node: dict[str, Any] = manifest["nodes"]["model.shop.customers"]
    assert node["description"] == test_case.expected_description
    assert {
        name: node["columns"][name]["description"]
        for name in test_case.expected_column_descriptions
    } == test_case.expected_column_descriptions
    dag_nodes: dict[str, dict[str, Any]] = {
        dag_node["name"]: dag_node for dag_node in json.loads(dag.stdout)["nodes"]
    }
    assert dag_nodes["customers"]["description"] == test_case.expected_description
