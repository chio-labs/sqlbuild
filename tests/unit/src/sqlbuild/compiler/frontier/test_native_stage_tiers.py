"""Each engine runs exactly the native stages whose registered tier it includes."""

from __future__ import annotations

from itertools import compress

import pytest

from sqlbuild.compiler.frontier.constants import (
    COMPILER_ENGINE_ENV_VAR,
    ENGINE_NATIVE_STAGE_TIERS,
    NATIVE_STAGE_TIERS,
)
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import CompilerEngine, NativeStage
from tests.unit.src.sqlbuild.compiler.frontier._test_types import (
    DefaultEngineStageTestCase,
    NativeStageCouplingTestCase,
    NativeStageTierTestCase,
)


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
            expected_enabled=True,
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
            description="python_model_config",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.MODEL_CONFIG,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_model_config",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.MODEL_CONFIG,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_preview_model_config",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.MODEL_CONFIG,
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
            expected_enabled=True,
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
            expected_enabled=True,
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
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_preview_model_loop",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.MODEL_LOOP,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_macro_calls",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.MACRO_CALLS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="python_macro_call_store",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.MACRO_CALL_STORE,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_macro_calls",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.MACRO_CALLS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_macro_call_store",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.MACRO_CALL_STORE,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_preview_macro_calls",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.MACRO_CALLS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_preview_macro_call_store",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.MACRO_CALL_STORE,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_attachments",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.ATTACHMENTS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_attachments",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.ATTACHMENTS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="native_preview_attachments",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.ATTACHMENTS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_type_system",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.TYPE_SYSTEM,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_type_system",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.TYPE_SYSTEM,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_type_system",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.TYPE_SYSTEM,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_model_analysis",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.MODEL_ANALYSIS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_model_analysis",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.MODEL_ANALYSIS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_model_analysis",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.MODEL_ANALYSIS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_semantic_checks",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.SEMANTIC_CHECKS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_semantic_checks",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.SEMANTIC_CHECKS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_semantic_checks",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.SEMANTIC_CHECKS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_contracts",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.CONTRACTS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_contracts",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.CONTRACTS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_contracts",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.CONTRACTS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_lineage_facts",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.LINEAGE_FACTS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_lineage_facts",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.LINEAGE_FACTS,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_lineage_facts",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.LINEAGE_FACTS,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_rich_lineage",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.RICH_LINEAGE,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_rich_lineage",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.RICH_LINEAGE,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_rich_lineage",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.RICH_LINEAGE,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_sql_test_glue",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.SQL_TEST_GLUE,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_sql_test_glue",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.SQL_TEST_GLUE,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_sql_test_glue",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.SQL_TEST_GLUE,
            expected_enabled=True,
        ),
        NativeStageTierTestCase(
            description="python_project_assembly",
            engine=CompilerEngine.PYTHON,
            stage=NativeStage.PROJECT_ASSEMBLY,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_project_assembly",
            engine=CompilerEngine.NATIVE,
            stage=NativeStage.PROJECT_ASSEMBLY,
            expected_enabled=False,
        ),
        NativeStageTierTestCase(
            description="native_preview_project_assembly",
            engine=CompilerEngine.NATIVE_PREVIEW,
            stage=NativeStage.PROJECT_ASSEMBLY,
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


@pytest.mark.parametrize(
    "test_case",
    [
        DefaultEngineStageTestCase(
            description="discovery_and_rendering_native_analysis_python",
            expected_enabled=frozenset(
                {
                    NativeStage.DISCOVERY,
                    NativeStage.DECLARATION_SCOPES,
                    NativeStage.MODEL_CONFIG,
                    NativeStage.REFERENCE_EXTRACTION,
                    NativeStage.DECLARATION_FILES,
                    NativeStage.MODEL_LOOP,
                    NativeStage.MACRO_CALLS,
                    NativeStage.MACRO_CALL_STORE,
                    NativeStage.ATTACHMENTS,
                }
            ),
            expected_disabled=frozenset(
                {
                    NativeStage.TYPE_SYSTEM,
                    NativeStage.MODEL_ANALYSIS,
                    NativeStage.SEMANTIC_CHECKS,
                    NativeStage.CONTRACTS,
                    NativeStage.LINEAGE_FACTS,
                    NativeStage.RICH_LINEAGE,
                    NativeStage.SQL_TEST_GLUE,
                    NativeStage.PROJECT_ASSEMBLY,
                }
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_engine_selection_when_checking_native_stages_then_rendering_runs_natively(
    test_case: DefaultEngineStageTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(COMPILER_ENGINE_ENV_VAR, raising=False)

    assert {stage: native_stage_enabled(stage) for stage in NativeStage} == {
        **dict.fromkeys(test_case.expected_enabled, True),
        **dict.fromkeys(test_case.expected_disabled, False),
    }


@pytest.mark.parametrize(
    "test_case",
    [
        NativeStageCouplingTestCase(
            description=(
                "semantic checks normalize types with the native type system unconditionally, "
                "while Python only does so where the type system stage runs natively"
            ),
            dependent=NativeStage.SEMANTIC_CHECKS,
            dependency=NativeStage.TYPE_SYSTEM,
            expected_engines_without_dependency=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_coupled_native_stages_when_reading_tiers_then_dependent_never_runs_alone(
    test_case: NativeStageCouplingTestCase,
) -> None:
    engines: tuple[CompilerEngine, ...] = tuple(ENGINE_NATIVE_STAGE_TIERS)
    dependent_engines: frozenset[CompilerEngine] = frozenset(
        compress(
            engines,
            (
                NATIVE_STAGE_TIERS[test_case.dependent] in tiers
                for tiers in ENGINE_NATIVE_STAGE_TIERS.values()
            ),
        )
    )
    dependency_engines: frozenset[CompilerEngine] = frozenset(
        compress(
            engines,
            (
                NATIVE_STAGE_TIERS[test_case.dependency] in tiers
                for tiers in ENGINE_NATIVE_STAGE_TIERS.values()
            ),
        )
    )

    assert dependent_engines - dependency_engines == (test_case.expected_engines_without_dependency)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
