from collections.abc import Callable

import pytest

import sqlbuild._native as native
from sqlbuild import _native
from sqlbuild._native import NativeRulesRequest
from sqlbuild.rule_engine.models import NativeRulesEvaluation


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

    identity: str = _native.compiled_code_identity()
    monkeypatch.setattr(_native, "compiled_code_identity", lambda: f"{identity}-rebuilt")
