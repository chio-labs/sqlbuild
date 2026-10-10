from collections.abc import Callable

import pytest

from sqlbuild._native import NativeRulesRequest
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.rule_engine._helpers.engine import native
from sqlbuild.rule_engine._helpers.run import native_rows
from sqlbuild.rule_engine.models import NativeRulesEvaluation

PREVIEW_ENGINE: str = "native-preview"


def use_preview_engine(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Select the engine that builds the built-in rules request natively."""

    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, PREVIEW_ENGINE)


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
    evaluate: Callable[[NativeRulesRequest], NativeRulesEvaluation] = (
        native_rows.evaluate_rules_request
    )

    def recording(request: NativeRulesRequest) -> NativeRulesEvaluation:
        evaluation: NativeRulesEvaluation = evaluate(request)
        reused.append(evaluation.reused)
        return evaluation

    monkeypatch.setattr(native, "evaluate_rules_request", recording)
    return reused


def rebuild_identity(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the compiled code changed, as after installing another build."""

    identity: str = native_rows.compiled_code_identity()
    monkeypatch.setattr(native_rows, "compiled_code_identity", lambda: f"{identity}-rebuilt")
