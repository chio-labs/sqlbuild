"""On-disk compiler stores are namespaced by engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.main.engine_cache_name import engine_cache_name
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.unit.src.sqlbuild.compiler.frontier._test_types import (
    EngineCacheNameTestCase,
    EngineStorePathsTestCase,
)
from tests.unit.src.sqlbuild.compiler.frontier.helpers import store_paths


@pytest.mark.parametrize(
    "test_case",
    [
        EngineCacheNameTestCase(
            description="native_gets_versioned_suffix",
            engine=CompilerEngine.NATIVE,
            base="compiler",
            expected_name="compiler-native-v1",
        ),
        EngineCacheNameTestCase(
            description="native_rules_cache",
            engine=CompilerEngine.NATIVE,
            base="rules-cache",
            expected_name="rules-cache-native-v1",
        ),
        EngineCacheNameTestCase(
            description="native_preview_gets_its_own_suffix",
            engine=CompilerEngine.NATIVE_PREVIEW,
            base="compiler",
            expected_name="compiler-native-preview-v1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_naming_store_then_only_native_engines_are_suffixed(
    test_case: EngineCacheNameTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine.value)

    assert engine_cache_name(test_case.base) == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    [
        EngineStorePathsTestCase(
            description="native_paths_separate",
            engine=CompilerEngine.NATIVE,
            expected_paths=(
                "target/cache/compiler-native-v1",
                "target/cache/compiler-native-v1",
                "target/cache/compiler-native-v1/declaration-scopes-v2",
                "target/rules-cache-native-v1/bulk/sql.json",
            ),
        ),
        EngineStorePathsTestCase(
            description="native_preview_paths_separate",
            engine=CompilerEngine.NATIVE_PREVIEW,
            expected_paths=(
                "target/cache/compiler-native-preview-v1",
                "target/cache/compiler-native-preview-v1",
                "target/cache/compiler-native-preview-v1/declaration-scopes-v2",
                "target/rules-cache-native-preview-v1/bulk/sql.json",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_resolving_stores_then_each_engine_owns_its_paths(
    test_case: EngineStorePathsTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine.value)

    assert store_paths(tmp_path) == test_case.expected_paths


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
