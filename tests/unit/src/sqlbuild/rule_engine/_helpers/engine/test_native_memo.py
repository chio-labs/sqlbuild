from pathlib import Path

import pytest

import sqlbuild._native as native_module
from sqlbuild.rule_engine.models import RulesResult
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    NativeBuildIdentityTestCase,
    NativeMemoTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import (
    evaluate_contract_rule,
    record_native_evaluations,
)


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


@pytest.mark.parametrize(
    "test_case",
    [NativeBuildIdentityTestCase("memoized response follows the native build", 1, 0)],
    ids=lambda case: case.description,
)
def test_given_memoized_response_from_another_native_build_when_evaluating_then_rules_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: NativeBuildIdentityTestCase,
) -> None:
    config_values: dict[str, object] = {"materialized": "table"}
    cold: RulesResult = evaluate_contract_rule(
        config_values=config_values, project_dir=tmp_path, cache_enabled=True
    )
    native_calls: list[str] = record_native_evaluations(monkeypatch=monkeypatch)
    monkeypatch.setattr(native_module, "BUILD_IDENTITY", f"{native_module.BUILD_IDENTITY}-rebuilt")
    rebuilt: RulesResult = evaluate_contract_rule(
        config_values=config_values, project_dir=tmp_path, cache_enabled=True
    )
    rebuilt_calls: int = len(native_calls)
    warm: RulesResult = evaluate_contract_rule(
        config_values=config_values, project_dir=tmp_path, cache_enabled=True
    )

    assert rebuilt_calls == test_case.expected_rebuilt_evaluations
    assert len(native_calls) - rebuilt_calls == test_case.expected_warm_evaluations
    assert rebuilt.findings == warm.findings == cold.findings


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
