"""Custom-rule results are reused only when every fact the invocation read is unchanged."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.models import CustomRulesOutcome
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    CustomRuleReadTrackingTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import (
    evaluate_cached_custom_rules,
    two_model_project,
    write_rule,
)

_CUSTOMERS_SQL: str = "SELECT 1 AS customer_id"
_FLAG_ORDERS: str = (
    '    return [ctx.finding(subject=model)] if model.name == "orders" and {condition} else []'
)


@pytest.mark.parametrize(
    "test_case",
    (
        CustomRuleReadTrackingTestCase(
            description="own SQL read reuses the unedited subject",
            body="_ = ctx.sql.for_model(model).expanded.source\n"
            + _FLAG_ORDERS.format(condition="True"),
            expected_hits_after_edit=1,
        ),
        CustomRuleReadTrackingTestCase(
            description="reading every model SQL invalidates every subject",
            body="sources = [ctx.sql.for_model(item).expanded.source "
            "for item in ctx.project.models]\n" + _FLAG_ORDERS.format(condition="len(sources) > 1"),
            expected_hits_after_edit=0,
        ),
        CustomRuleReadTrackingTestCase(
            description="unchanged contracts of every model keep both subjects",
            body="enforced = [ctx.contracts.enforced(item) for item in ctx.project.models]\n"
            + _FLAG_ORDERS.format(condition="not any(enforced)"),
            expected_hits_after_edit=2,
        ),
        CustomRuleReadTrackingTestCase(
            description="changed contract of another model invalidates readers",
            body="enforced = [ctx.contracts.enforced(item) for item in ctx.project.models]\n"
            + _FLAG_ORDERS.format(condition="not any(enforced)"),
            expected_hits_after_edit=0,
            edited_customers_sql=_CUSTOMERS_SQL,
            edited_customers_config={"contract": "enforced"},
        ),
        CustomRuleReadTrackingTestCase(
            description="module-level memo makes the rule untracked",
            module_prelude="_MEMO: dict[str, object] = {}",
            body="if 'sql' not in _MEMO:\n"
            "        _MEMO['sql'] = [ctx.sql.for_model(item).expanded.source "
            "for item in ctx.project.models]\n"
            + _FLAG_ORDERS.format(condition="'SELECT 2' in ' '.join(_MEMO['sql'])"),
            expected_hits_after_edit=0,
        ),
        CustomRuleReadTrackingTestCase(
            description="cached helper makes the rule untracked",
            module_prelude=(
                "import functools\n\n"
                "@functools.cache\n"
                "def _sources(ctx: RuleContext) -> str:\n"
                "    return ' '.join(ctx.sql.for_model(item).expanded.source "
                "for item in ctx.project.models)\n"
            ),
            body=_FLAG_ORDERS.format(condition="'SELECT 2' in _sources(ctx)").strip(),
            expected_hits_after_edit=0,
        ),
        CustomRuleReadTrackingTestCase(
            description="private view access makes the rule untracked",
            body="_ = ctx.sql._models\n" + _FLAG_ORDERS.format(condition="True"),
            expected_hits_after_edit=0,
        ),
        CustomRuleReadTrackingTestCase(
            description="context attribute state makes the rule untracked",
            body="ctx.seen = model.name\n" + _FLAG_ORDERS.format(condition="True"),
            expected_hits_after_edit=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_recorded_reads_when_one_model_changes_then_only_dependent_results_rerun(
    tmp_path: Path,
    test_case: CustomRuleReadTrackingTestCase,
) -> None:
    _ = write_rule(root=tmp_path, body=test_case.body, module_import=test_case.module_prelude)
    original: CompiledProject = two_model_project(customers_sql=_CUSTOMERS_SQL, customers_config={})
    edited: CompiledProject = two_model_project(
        customers_sql=test_case.edited_customers_sql,
        customers_config=test_case.edited_customers_config,
    )

    cold: CustomRulesOutcome = evaluate_cached_custom_rules(
        project=original, project_dir=tmp_path, cache_enabled=True
    )
    warm: CustomRulesOutcome = evaluate_cached_custom_rules(
        project=original, project_dir=tmp_path, cache_enabled=True
    )
    after_edit: CustomRulesOutcome = evaluate_cached_custom_rules(
        project=edited, project_dir=tmp_path, cache_enabled=True
    )
    oracle: CustomRulesOutcome = evaluate_cached_custom_rules(
        project=edited, project_dir=tmp_path, cache_enabled=False
    )

    assert (cold.cache_hits, cold.cache_misses) == (0, 2)
    assert (warm.cache_hits, warm.cache_misses) == (2, 0)
    assert warm.findings == cold.findings
    assert (after_edit.cache_hits, after_edit.cache_misses) == (
        test_case.expected_hits_after_edit,
        2 - test_case.expected_hits_after_edit,
    )
    assert after_edit.findings == oracle.findings


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
