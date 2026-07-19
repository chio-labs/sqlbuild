from textwrap import dedent

import pytest
from fensu import RuleCase, RuleResult, evaluate_rule

from scripts.fensu_policy.rules.canonical_operations import (
    color_capability_entry,
    dbt_graph_projection,
    dbt_reference_resolution,
    selector_marker_parsing,
    single_macro_load_site,
    source_freshness_batch_write,
    source_freshness_sql_ownership,
)
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="raw color capability import faults",
            path="src/sqlbuild/example/main/build.py",
            source=(
                "from sqlbuild.presentation._helpers.terminal_capabilities import supports_color\n"
            ),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="public color capability import passes",
            path="src/sqlbuild/example/main/build.py",
            source="from sqlbuild.presentation.main.supports_color import supports_color\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_import_when_checking_color_entry_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=color_capability_entry,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="ad hoc dbt reference comparison faults",
            path="src/sqlbuild/integrations/dbt/_helpers/planning/ref_scan.py",
            source="is_dbt = reference.ref_kind == SqlReferenceKind.DBT_REF\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="qualified dbt reference comparison faults",
            path="src/sqlbuild/integrations/dbt/_helpers/planning/ref_scan.py",
            source=("is_dbt = reference.ref_kind == references.SqlReferenceKind.DBT_REF\n"),
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="central dbt reference comparison passes",
            path="src/sqlbuild/integrations/dbt/_helpers/manifest/sqlbuild_refs.py",
            source="is_dbt = reference.ref_kind == SqlReferenceKind.DBT_REF\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_code_when_checking_reference_resolution_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=dbt_reference_resolution,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="ad hoc graph key construction faults",
            path="src/sqlbuild/integrations/dbt/_helpers/planning/projection.py",
            source="key = GraphNodeKey(node_type='dbt', node_name='model')\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="qualified graph key construction faults per call",
            path="src/sqlbuild/integrations/dbt/_helpers/planning/projection.py",
            source=(
                "graph = models.GraphNodeKey(node_type='dbt', node_name='model')\n"
                "stale = models.SelectionStalenessNodeKey(node_type='dbt', node_name='model')\n"
            ),
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="central graph key construction passes",
            path="src/sqlbuild/integrations/dbt/_helpers/planning/graph_projection.py",
            source="key = GraphNodeKey(node_type='dbt', node_name='model')\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_code_when_checking_graph_projection_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=dbt_graph_projection,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="ad hoc selector parsing faults for each operation",
            path="src/sqlbuild/integrations/dbt/_helpers/selection/core.py",
            source="result = raw.startswith('+'), raw.lstrip('+')\n",
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="central selector parsing passes",
            path="src/sqlbuild/compiler/planner/main/selection/selector_expansion.py",
            source="result = raw.startswith('+'), raw.lstrip('+')\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selector_code_when_checking_marker_parsing_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=selector_marker_parsing,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="singular freshness import and call both fault",
            path="src/sqlbuild/example/main/build.py",
            source=dedent(
                """
                from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_record

                write_source_freshness_record()
                """
            ),
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="batch freshness writer passes",
            path="src/sqlbuild/example/main/build.py",
            source="write_source_freshness_records()\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_freshness_code_when_checking_batch_write_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=source_freshness_batch_write,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="runtime freshness INSERT faults",
            path="src/sqlbuild/example/main/build.py",
            source="SOURCE_FRESHNESS = 'table'\nsql = 'INSERT INTO table VALUES (1)'\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="adapter freshness INSERT passes",
            path="src/sqlbuild/adapters/example/classes/example_adapter.py",
            source="SOURCE_FRESHNESS = 'table'\nsql = 'INSERT INTO table VALUES (1)'\n",
            expected_fault_count=0,
        ),
        CustomRuleTestCase(
            description="tooling freshness INSERT faults",
            path="scripts/example/main/probe.py",
            source="SOURCE_FRESHNESS = 'table'\nsql = 'INSERT INTO table VALUES (1)'\n",
            expected_fault_count=1,
            scope="tooling",
            scope_root="scripts",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_freshness_code_when_checking_sql_ownership_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=source_freshness_sql_ownership,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="secondary macro import and call both fault",
            path="src/sqlbuild/example/main/build.py",
            source=dedent(
                """
                from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros

                loaded = load_project_macros(())
                """
            ),
            expected_fault_count=2,
        ),
        CustomRuleTestCase(
            description="qualified secondary macro call faults",
            path="src/sqlbuild/example/main/build.py",
            source="loaded = macros.load_project_macros(())\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="compile input macro load passes",
            path="src/sqlbuild/compiler/compile/main/_build_compile_inputs.py",
            source="loaded = load_project_macros(())\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compile_code_when_checking_macro_load_site_then_matches_contract(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=single_macro_load_site,
        test_case=RuleCase(
            description=test_case.description,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            path=test_case.path,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
            files=test_case.files,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count
