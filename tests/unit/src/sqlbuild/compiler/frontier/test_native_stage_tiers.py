"""Each engine runs exactly the native stages whose registered tier it includes."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import CompilerEngine, NativeStage
from tests.unit.src.sqlbuild.compiler.frontier._test_types import NativeStageTierTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        NativeStageTierTestCase(
            description="python_discovery",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.DISCOVERY,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="python_declaration_scopes",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.DECLARATION_SCOPES,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_discovery",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.DISCOVERY,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_declaration_scopes",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.DECLARATION_SCOPES,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_discovery",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.DISCOVERY,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_preview_declaration_scopes",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.DECLARATION_SCOPES,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_reference_extraction",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.REFERENCE_EXTRACTION,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_reference_extraction",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.REFERENCE_EXTRACTION,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_reference_extraction",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.REFERENCE_EXTRACTION,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_declaration_files",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.DECLARATION_FILES,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_declaration_files",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.DECLARATION_FILES,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_declaration_files",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.DECLARATION_FILES,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_model_loop",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.MODEL_LOOP,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_model_loop",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.MODEL_LOOP,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_model_loop",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.MODEL_LOOP,
            expected_enabled=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_checking_native_stage_then_only_its_tiers_run(
    test_case: NativeStageTierTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine.value)

    assert native_stage_enabled(test_case.stage) is test_case.expected_enabled


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
