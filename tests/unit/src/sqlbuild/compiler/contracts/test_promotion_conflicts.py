from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.contracts.main.promotion_conflicts import promotion_conflict_diagnostics
from tests.unit.src.sqlbuild.compiler.contracts._test_types import PromotionConflictTestCase
from tests.unit.src.sqlbuild.compiler.contracts.helpers import make_promotion_project

_ENFORCED_TABLE: dict[str, object] = {"materialized": "table", "contract": "enforced"}


@pytest.mark.parametrize(
    "test_case",
    [
        PromotionConflictTestCase(
            description="explicit immediate reports every enforced table-lifecycle model",
            model_configs=(
                ("order_totals", _ENFORCED_TABLE),
                ("customer_orders", {"contract": "enforced"}),
                ("order_events", {"materialized": "incremental", "contract": "enforced"}),
                (
                    "order_batches",
                    {
                        "materialized": "incremental",
                        "incremental_mode": "microbatch",
                        "contract": "enforced",
                    },
                ),
                ("order_view", {"materialized": "view", "contract": "enforced"}),
                ("order_history", {"materialized": "snapshot", "contract": "enforced"}),
                ("raw_totals", {"materialized": "table"}),
            ),
            table_promotion_mode="immediate",
            adapter_default="staged",
            settings_file="sqlbuild_project.toml",
            expected_resource_names=("order_totals", "customer_orders", "order_events"),
            expected_help_fragments=(
                'sqlbuild_project.toml sets [settings] table_promotion_mode = "immediate"',
                "remove that line to use the default staged promotion, or set this in "
                "sqlbuild_project.toml:",
                'table_promotion_mode = "staged"',
                "`contract enforced` in its MODEL header",
            ),
        ),
        PromotionConflictTestCase(
            description="local override names the local file",
            model_configs=(("order_totals", _ENFORCED_TABLE),),
            table_promotion_mode="immediate",
            adapter_default="staged",
            settings_file="sqlbuild_local.toml",
            expected_resource_names=("order_totals",),
            expected_help_fragments=(
                'sqlbuild_local.toml sets [settings] table_promotion_mode = "immediate"',
            ),
        ),
        PromotionConflictTestCase(
            description="immediate adapter default asks for an explicit staged setting",
            model_configs=(("order_totals", _ENFORCED_TABLE),),
            table_promotion_mode=None,
            adapter_default="immediate",
            settings_file="sqlbuild_project.toml",
            expected_resource_names=("order_totals",),
            expected_help_fragments=(
                "sqlbuild_project.toml does not set [settings] table_promotion_mode, so it "
                'defaults to "immediate"',
                "to validate enforced contracts before promotion, set this in "
                "sqlbuild_project.toml:",
            ),
        ),
        PromotionConflictTestCase(
            description="staged setting reports nothing",
            model_configs=(("order_totals", _ENFORCED_TABLE),),
            table_promotion_mode="staged",
            adapter_default="staged",
            settings_file="sqlbuild_project.toml",
            expected_resource_names=(),
        ),
        PromotionConflictTestCase(
            description="unset setting with staged adapter default reports nothing",
            model_configs=(("order_totals", _ENFORCED_TABLE),),
            table_promotion_mode=None,
            adapter_default="staged",
            settings_file="sqlbuild_project.toml",
            expected_resource_names=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_promotion_setting_when_checking_contracts_then_reports_conflicting_models(
    test_case: PromotionConflictTestCase,
) -> None:
    diagnostics: tuple[CompilerDiagnostic, ...] = promotion_conflict_diagnostics(
        project=make_promotion_project(
            model_configs=test_case.model_configs,
            table_promotion_mode=test_case.table_promotion_mode,
        ),
        adapter_default=TablePromotionMode(test_case.adapter_default),
        settings_file=test_case.settings_file,
    )

    assert tuple(item.resource_name for item in diagnostics) == test_case.expected_resource_names
    assert all(item.code == "K011" and item.is_error for item in diagnostics)
    for diagnostic in diagnostics:
        for fragment in test_case.expected_help_fragments:
            assert fragment in str(diagnostic.help)
