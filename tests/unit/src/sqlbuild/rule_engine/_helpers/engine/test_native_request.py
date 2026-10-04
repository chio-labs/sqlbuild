from pathlib import Path
from typing import NoReturn

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine._helpers.engine import native
from sqlbuild.rule_engine.models import RulesCacheConfig, RulesConfig
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    NativeRequestBuildErrorTestCase,
    NativeRequestEncodeErrorTestCase,
)
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRequestBuildErrorTestCase(
            description="type error", expected_error=TypeError("orders payload is not a mapping")
        ),
        NativeRequestBuildErrorTestCase(
            description="value error", expected_error=ValueError("orders payload has no name")
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_request_builder_when_evaluating_native_then_error_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_case: NativeRequestBuildErrorTestCase,
) -> None:
    project: CompiledProject = build_project(
        name="orders", relative_path="models/orders.sql", sql="SELECT 1", config_values={}
    )
    started: list[str] = []

    def failing_model_payloads(**_: object) -> NoReturn:
        raise test_case.expected_error

    def record_custom_start(**_: object) -> None:
        started.append("custom")

    def record_native_call(*_: object) -> str:
        started.append("native")
        return "{}"

    monkeypatch.setattr(native, "_model_payloads", failing_model_payloads)
    monkeypatch.setattr(native, "start_custom_rules", record_custom_start)
    monkeypatch.setattr(native._native, "evaluate_rules_parts", record_native_call)

    with pytest.raises(type(test_case.expected_error)) as raised:
        native.evaluate_native(
            project=project,
            config=RulesConfig(cache=RulesCacheConfig(enabled=False)),
            project_dir=tmp_path,
            catalogue=(),
        )

    assert raised.value is test_case.expected_error
    assert started == []


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRequestEncodeErrorTestCase(
            description="integer beyond 64 bits", rejected_value=2**70, expected_message="64-bit"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_value_the_encoder_rejects_when_evaluating_native_then_rules_error_is_raised(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_case: NativeRequestEncodeErrorTestCase,
) -> None:
    project: CompiledProject = build_project(
        name="orders", relative_path="models/orders.sql", sql="SELECT 1", config_values={}
    )
    started: list[str] = []

    def oversized_model_payloads(**_: object) -> list[dict[str, object]]:
        return [{"name": "orders", "priority": test_case.rejected_value}]

    def record_custom_start(**_: object) -> None:
        started.append("custom")

    def record_native_call(*_: object) -> str:
        started.append("native")
        return "{}"

    monkeypatch.setattr(native, "_model_payloads", oversized_model_payloads)
    monkeypatch.setattr(native, "start_custom_rules", record_custom_start)
    monkeypatch.setattr(native._native, "evaluate_rules_parts", record_native_call)

    with pytest.raises(native.RulesError, match=test_case.expected_message):
        native.evaluate_native(
            project=project,
            config=RulesConfig(cache=RulesCacheConfig(enabled=False)),
            project_dir=tmp_path,
            catalogue=(),
        )

    assert started == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
