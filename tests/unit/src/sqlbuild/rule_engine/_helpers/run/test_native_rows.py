"""Externally visible outcomes of the natively built rules request."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine._helpers.engine import native
from sqlbuild.rule_engine.models import RulesCacheConfig, RulesConfig, RulesResult
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import evaluate_contract_rule
from tests.unit.src.sqlbuild.rule_engine._helpers.run._test_types import (
    NativeRowsEncodeErrorTestCase,
    NativeRowsMemoTestCase,
)
from tests.unit.src.sqlbuild.rule_engine._helpers.run.helpers import (
    rebuild_identity,
    record_custom_starts,
    record_reuse,
)
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRowsEncodeErrorTestCase(
            description="integer beyond 64 bits", rejected_value=2**70, expected_message="64-bit"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_config_value_the_encoder_rejects_when_building_natively_then_rules_error_is_raised(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_case: NativeRowsEncodeErrorTestCase,
) -> None:
    started: list[str] = record_custom_starts(monkeypatch=monkeypatch)
    project: CompiledProject = build_project(
        name="orders",
        relative_path="models/orders.sql",
        sql="SELECT 1",
        config_values={"priority": test_case.rejected_value},
    )

    with pytest.raises(native.RulesError, match=test_case.expected_message):
        native.evaluate_native(
            project=project,
            config=RulesConfig(cache=RulesCacheConfig(enabled=False)),
            project_dir=tmp_path,
            catalogue=(),
        )

    assert started == []


@pytest.mark.parametrize(
    "test_case",
    [NativeRowsMemoTestCase("memoized response follows the native build", (False, False, True))],
    ids=lambda case: case.description,
)
def test_given_memoized_response_from_another_build_when_evaluating_natively_then_rules_rerun(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_case: NativeRowsMemoTestCase,
) -> None:
    reused: list[bool] = record_reuse(monkeypatch=monkeypatch)
    config_values: dict[str, object] = {"materialized": "table"}

    cold: RulesResult = evaluate_contract_rule(
        config_values=config_values, project_dir=tmp_path, cache_enabled=True
    )
    rebuild_identity(monkeypatch=monkeypatch)
    rebuilt: RulesResult = evaluate_contract_rule(
        config_values=config_values, project_dir=tmp_path, cache_enabled=True
    )
    warm: RulesResult = evaluate_contract_rule(
        config_values=config_values, project_dir=tmp_path, cache_enabled=True
    )

    assert tuple(reused) == test_case.expected_reused
    assert rebuilt.findings == warm.findings == cold.findings
