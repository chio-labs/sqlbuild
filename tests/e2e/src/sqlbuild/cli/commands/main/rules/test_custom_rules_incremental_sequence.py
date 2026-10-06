"""Incremental custom Rules across split hosts must equal a cache-free compile after every edit."""

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    replace_project_text,
    write_project_file,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import (
    BrokenInvalidationChainCase,
    RulesCacheEditCase,
    RulesEditChainCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules.helpers import (
    STALE_SOURCE_FACTS_SITECUSTOMIZE,
    custom_rules_edit_chain,
    rule_cache_counts,
    rules_compile_outcome,
)

CONFIG: str = "sqlbuild_project.toml"
ORDER_TOTALS: str = "models/marts/order_totals.sql"
SOURCES: str = "sources/raw.yml"
APPROVED: str = "rules/approved_sources.yaml"
CUSTOM_EDIT_SEQUENCE: tuple[RulesCacheEditCase, ...] = (
    RulesCacheEditCase(
        "model_sql_edited",
        lambda root: replace_project_text(root, ORDER_TOTALS, "amount > 7", "amount > 9"),
    ),
    RulesCacheEditCase(
        "source_in_shared_file_renamed",
        lambda root: replace_project_text(root, SOURCES, "raw_products", "raw_returns"),
    ),
    RulesCacheEditCase(
        "tracked_rule_input_edited",
        lambda root: replace_project_text(
            root, APPROVED, "raw_customers\n", "raw_customers\nraw_returns\n"
        ),
    ),
    RulesCacheEditCase(
        "mart_added",
        lambda root: write_project_file(
            root,
            "models/marts/customer_totals.sql",
            'MODEL (description "Customer totals");\n\n'
            'SELECT customer_id FROM __ref("stg_customers")\n',
        ),
    ),
    RulesCacheEditCase(
        "model_removed",
        lambda root: (root / "models/intermediate/orders_007.sql").unlink(),
    ),
    RulesCacheEditCase(
        "rules_cache_disabled",
        lambda root: replace_project_text(
            root,
            CONFIG,
            "[rules.thresholds]",
            "[rules.cache]\nenabled = false\n\n[rules.thresholds]",
        ),
    ),
    RulesCacheEditCase(
        "source_edited_without_cache",
        lambda root: replace_project_text(root, SOURCES, "raw_returns", "raw_refunds"),
    ),
    RulesCacheEditCase(
        "rules_cache_enabled",
        lambda root: replace_project_text(root, CONFIG, "[rules.cache]\nenabled = false\n\n", ""),
    ),
    RulesCacheEditCase(
        "source_restored_with_cache",
        lambda root: replace_project_text(root, SOURCES, "raw_refunds", "raw_returns"),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    (
        RulesEditChainCase(
            description="model_source_input_and_cache_toggle_edits",
            edits=CUSTOM_EDIT_SEQUENCE,
            expected_cold_codes=("XSQBRORD102", "XSQBRORD103", "XSQBRORD201"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_warm_custom_rules_when_applying_edit_chain_then_every_compile_equals_uncached(
    tmp_path: Path, test_case: RulesEditChainCase
) -> None:
    cold, edited, oracles = custom_rules_edit_chain(root=tmp_path, edits=test_case.edits)
    rewarmed: tuple[int, str, str] = rules_compile_outcome(tmp_path / "orders")

    assert cold[0] == test_case.expected_exit_code
    assert all(f'"{code}"' in cold[1] for code in test_case.expected_cold_codes), cold[1]
    assert edited == oracles
    assert {outcome[0] for outcome in edited} == {test_case.expected_exit_code}
    assert '"XSQBRORD101"' in edited[0][1]
    assert ("raw_returns" in edited[1][1], "raw_returns" in edited[2][1]) == (True, False)
    assert rewarmed == oracles[-1]
    assert rule_cache_counts(tmp_path / "orders")[1] == 0


@pytest.mark.parametrize(
    "test_case",
    (
        BrokenInvalidationChainCase(
            description="stale_shared_source_digests",
            edits=CUSTOM_EDIT_SEQUENCE,
            stale_digests_sitecustomize=STALE_SOURCE_FACTS_SITECUSTOMIZE,
            expected_first_divergent_edit="source_in_shared_file_renamed",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_broken_invalidation_when_applying_edit_chain_then_oracle_detects_divergence(
    tmp_path: Path, test_case: BrokenInvalidationChainCase
) -> None:
    write_project_file(tmp_path / "site", "sitecustomize.py", test_case.stale_digests_sitecustomize)

    _, edited, oracles = custom_rules_edit_chain(
        root=tmp_path, edits=test_case.edits, environment=(("PYTHONPATH", str(tmp_path / "site")),)
    )
    matches: list[bool] = [
        outcome == oracle for outcome, oracle in zip(edited, oracles, strict=True)
    ]

    assert test_case.edits[matches.index(False)].description == (
        test_case.expected_first_divergent_edit
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
