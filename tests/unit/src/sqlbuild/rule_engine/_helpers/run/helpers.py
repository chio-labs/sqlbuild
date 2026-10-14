from collections.abc import Callable

import pytest

from sqlbuild import _native
from sqlbuild._native import NativeRulesRequest
from sqlbuild.compiler.frontier.main import compiled_code_identity as code_identity
from sqlbuild.rule_engine._helpers.engine import custom_dispatch as native
from sqlbuild.rule_engine.models import NativeRulesEvaluation


def record_custom_starts(*, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every custom-rule start instead of starting one."""

    started: list[str] = []

    def record_start(**_: object) -> None:
        started.append("custom")

    monkeypatch.setattr(native, "start_custom_rules", record_start)
    return started


def record_reuse(*, monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Record whether each natively evaluated request was answered from the response memo."""

    reused: list[bool] = []
    evaluate: Callable[[NativeRulesRequest], NativeRulesEvaluation] = _native.evaluate_rules_request

    def recording(request: NativeRulesRequest) -> NativeRulesEvaluation:
        evaluation: NativeRulesEvaluation = evaluate(request)
        reused.append(evaluation.reused)
        return evaluation

    monkeypatch.setattr(native, "evaluate_rules_request", recording)
    return reused


def rebuild_identity(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the compiled code changed, as after installing another build."""

    identity: str = code_identity.compiled_code_identity()
    monkeypatch.setattr(code_identity, "compiled_code_identity", lambda: f"{identity}-rebuilt")
