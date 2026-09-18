import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.contract_adoption._helpers.compare import compare_evidence
from sqlbuild.compiler.contract_adoption._helpers.repository_edits import (
    _declared_type_span,
    edit_model,
)
from sqlbuild.compiler.contract_adoption.models import ContractEvidence
from sqlbuild.compiler.discovery.models import ModelHeaderColumnSpan
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily
from tests.unit.src.sqlbuild.compiler.contract_adoption._helpers._test_types import (
    DeclaredTypeSpanTestCase,
    DynamicContractAdoptionTestCase,
)
from tests.unit.src.sqlbuild.compiler.contracts.helpers import make_contract_project


@pytest.mark.parametrize(
    "test_case",
    [
        DeclaredTypeSpanTestCase(
            description="nested type argument precedes the declared column type",
            contents="amount (audits [custom(type INT)], type INT)",
            declared_type="INT",
            expected_value="INT",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nested_type_key_when_locating_declared_type_then_returns_top_level_value(
    test_case: DeclaredTypeSpanTestCase,
) -> None:
    contents: str = test_case.contents
    metadata_start: int = contents.index("audits")
    metadata_end: int = contents.rindex(")")
    expected_start: int = contents.rindex(test_case.expected_value)

    result: tuple[int, int] | None = _declared_type_span(
        contents=contents,
        column_span=ModelHeaderColumnSpan(
            entry_start=0,
            entry_end=len(contents),
            metadata_start=metadata_start,
            metadata_end=metadata_end,
        ),
        declared_type=test_case.declared_type,
    )

    assert result == (expected_start, expected_start + len(test_case.expected_value))


@pytest.mark.parametrize(
    "test_case",
    (DynamicContractAdoptionTestCase(description="preserve dynamic family generation"),),
    ids=lambda case: case.description,
)
def test_given_dynamic_family_when_generating_contract_then_does_not_freeze_runtime_members(
    test_case: DynamicContractAdoptionTestCase,
) -> None:
    authored_sql: str = """MODEL (
  contract enforced,
  columns (customer_id (type INTEGER)),
  dynamic_columns (
    category_amounts (
      pivot_column category,
      value_column amount,
      aggregate MAX,
      type "DECIMAL(12,2)"
    )
  ),
);
SELECT * FROM category_amounts
"""
    model: CompiledModel = make_contract_project(
        declared_columns=(("customer_id", "INTEGER"),),
        inferred_columns=(("customer_id", "INTEGER"),),
        type_enforcement=True,
        contract="enforced",
        dynamic_columns=(
            SchemaDynamicColumnFamily(
                name="category_amounts",
                pivot_column="category",
                value_column="amount",
                aggregate="MAX",
                type="DECIMAL(12,2)",
            ),
        ),
        authored_sql=authored_sql,
    ).models[0]

    edited, reason = edit_model(
        model=model,
        physical_columns=(
            ColumnInfo(name="customer_id", type="INTEGER"),
            ColumnInfo(name="books", type="DECIMAL(12,2)"),
            ColumnInfo(name="games", type="DECIMAL(12,2)"),
        ),
        overwrite=False,
    )

    assert reason == test_case.expected_reason
    assert edited == authored_sql
    assert "books (" not in edited
    assert "games (" not in edited


@pytest.mark.parametrize(
    "test_case",
    (
        DynamicContractAdoptionTestCase(
            description="compare dynamic member types",
            expected_matching_findings=0,
            expected_mismatching_findings=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_family_when_inspecting_contract_then_compares_generated_member_types(
    test_case: DynamicContractAdoptionTestCase,
) -> None:
    evidence: ContractEvidence = ContractEvidence(
        resource_type=CompiledResourceType.MODEL,
        resource_name="customer_category_amounts",
        database=None,
        schema="main",
        relation="customer_category_amounts",
        declared_columns=(ColumnInfo(name="customer_id", type="INTEGER"),),
        physical_columns=None,
        source_path=None,
        dynamic_columns=(
            SchemaDynamicColumnFamily(
                name="category_amounts",
                pivot_column="category",
                value_column="amount",
                aggregate="MAX",
                type="DECIMAL(12,2)",
            ),
        ),
    )

    matching: ContractEvidence = compare_evidence(
        item=evidence,
        physical_columns=(
            ColumnInfo(name="customer_id", type="INTEGER"),
            ColumnInfo(name="books", type="DECIMAL(12,2)"),
        ),
        adapter=DuckDbAdapter(),
    )
    mismatching: ContractEvidence = compare_evidence(
        item=evidence,
        physical_columns=(
            ColumnInfo(name="customer_id", type="INTEGER"),
            ColumnInfo(name="books", type="VARCHAR"),
        ),
        adapter=DuckDbAdapter(),
    )

    assert len(matching.findings) == test_case.expected_matching_findings
    assert len(mismatching.findings) == test_case.expected_mismatching_findings
    assert mismatching.findings[0].column_name == "books"
    assert mismatching.findings[0].declared_type == "DECIMAL(12,2)"
