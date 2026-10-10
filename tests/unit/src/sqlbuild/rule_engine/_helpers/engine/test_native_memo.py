from pathlib import Path

import pytest

from sqlbuild.rule_engine.models import RulesResult
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import NativeMemoTestCase
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import evaluate_contract_rule


@pytest.mark.parametrize(
    "test_case",
    [
        NativeMemoTestCase(
            description="contract_enforced_after_warm_run",
            original_config={"materialized": "table"},
            edited_config={"materialized": "table", "contract": "enforced"},
            expected_original_codes=("SQBRCONTRACT101",),
            expected_edited_codes=(),
        ),
        NativeMemoTestCase(
            description="contract_removed_after_warm_run",
            original_config={"materialized": "table", "contract": "enforced"},
            edited_config={"materialized": "table"},
            expected_original_codes=(),
            expected_edited_codes=("SQBRCONTRACT101",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warm_built_in_memo_when_request_repeats_or_changes_then_matches_uncached(
    tmp_path: Path, test_case: NativeMemoTestCase
) -> None:
    cached_dir: Path = tmp_path / "cached"
    cached_dir.mkdir()

    first: RulesResult = evaluate_contract_rule(
        config_values=test_case.original_config, project_dir=cached_dir, cache_enabled=True
    )
    repeated: RulesResult = evaluate_contract_rule(
        config_values=test_case.original_config, project_dir=cached_dir, cache_enabled=True
    )
    edited: RulesResult = evaluate_contract_rule(
        config_values=test_case.edited_config, project_dir=cached_dir, cache_enabled=True
    )
    uncached_edited: RulesResult = evaluate_contract_rule(
        config_values=test_case.edited_config, project_dir=tmp_path, cache_enabled=False
    )

    assert tuple(finding.code for finding in first.findings) == test_case.expected_original_codes
    assert repeated.findings == first.findings
    assert (repeated.cache_misses, repeated.built_in_ms) == (0, 0)
    assert tuple(finding.code for finding in edited.findings) == test_case.expected_edited_codes
    assert edited.findings == uncached_edited.findings
    assert edited.cache_misses > 0


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
