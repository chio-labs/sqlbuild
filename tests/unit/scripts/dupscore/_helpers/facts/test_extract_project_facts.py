from __future__ import annotations

import pytest

from scripts.dupscore._helpers.facts import extract_project_facts
from scripts.dupscore.models import ClassFact, FunctionFact, ProjectFacts
from tests.unit.scripts.dupscore._helpers.facts._test_types import (
    ExtractCallsTestCase,
    ExtractFieldsTestCase,
    ExtractModulesTestCase,
)
from tests.unit.scripts.dupscore._helpers.facts.helpers import find_class, find_function

_PLANNER_SOURCE: str = (
    "from sqlbuild.alpha.shared_leaves.leaves import load_rows\n"
    "\n"
    "def run_plan() -> int:\n"
    "    return load_rows()\n"
)
_LEAVES_SOURCE: str = "def load_rows() -> int:\n    return 1\n"
_MODELS_SOURCE: str = (
    "from dataclasses import dataclass\n"
    "\n"
    "@dataclass(frozen=True)\n"
    "class PlanOptions:\n"
    "    select: str\n"
    "    exclude: str\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractModulesTestCase(
            description="extracts sorted analyzable modules",
            sources={
                "src/sqlbuild/alpha/planner/plan.py": _PLANNER_SOURCE,
                "src/sqlbuild/alpha/shared_leaves/leaves.py": _LEAVES_SOURCE,
            },
            expected_modules=(
                "sqlbuild.alpha.planner.plan",
                "sqlbuild.alpha.shared_leaves.leaves",
            ),
        ),
        ExtractModulesTestCase(
            description="excludes dbt integration modules and non-source paths",
            sources={
                "src/sqlbuild/integrations/dbt/adapter.py": "def hidden() -> None:\n    return None\n",
                "docs/example.py": "def ignored() -> None:\n    return None\n",
                "src/sqlbuild/beta/keep.py": "def kept() -> None:\n    return None\n",
            },
            expected_modules=("sqlbuild.beta.keep",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sources_when_extracting_facts_then_returns_expected_modules(
    test_case: ExtractModulesTestCase,
) -> None:
    facts: ProjectFacts = extract_project_facts(test_case.sources)

    assert tuple(module.module for module in facts.modules) == test_case.expected_modules


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractCallsTestCase(
            description="resolves imported project calls to their owning module",
            sources={
                "src/sqlbuild/alpha/planner/plan.py": _PLANNER_SOURCE,
                "src/sqlbuild/alpha/shared_leaves/leaves.py": _LEAVES_SOURCE,
            },
            function_qualified_name="sqlbuild.alpha.planner.plan::run_plan",
            expected_resolved_calls=("sqlbuild.alpha.shared_leaves.leaves::load_rows",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_imported_call_when_extracting_facts_then_resolves_call_target(
    test_case: ExtractCallsTestCase,
) -> None:
    facts: ProjectFacts = extract_project_facts(test_case.sources)

    function: FunctionFact = find_function(
        facts=facts,
        qualified_name=test_case.function_qualified_name,
    )
    assert function.resolved_calls == test_case.expected_resolved_calls


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractFieldsTestCase(
            description="extracts dataclass field names in declaration order",
            sources={"src/sqlbuild/alpha/planner/models.py": _MODELS_SOURCE},
            class_qualified_name="sqlbuild.alpha.planner.models::PlanOptions",
            expected_field_names=("select", "exclude"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dataclass_when_extracting_facts_then_returns_field_names(
    test_case: ExtractFieldsTestCase,
) -> None:
    facts: ProjectFacts = extract_project_facts(test_case.sources)

    class_fact: ClassFact = find_class(
        facts=facts,
        qualified_name=test_case.class_qualified_name,
    )
    assert class_fact.dataclass_like
    assert class_fact.field_names == test_case.expected_field_names
