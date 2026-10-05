from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from scripts.cold_compile_performance.models import RandomDagProject, RandomRenderProject


@dataclass(frozen=True)
class NativeRenderFixtureCase:
    description: str
    fixture: str
    expected_exit_code: int
    expected_minimum_native_models: int
    expected_differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeRenderProjectCase:
    description: str
    project: RandomRenderProject
    expected_exit_code: int
    expected_minimum_native_models: int
    expected_differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeRenderDagCase:
    description: str
    project: RandomDagProject
    expected_differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeRenderDenseCase:
    description: str
    model_count: int
    expected_native_models: int
    expected_fallback_models: int
    expected_differences: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeRenderMutationCase:
    description: str
    project: RandomRenderProject
    break_native: Callable[[pytest.MonkeyPatch], None]
    expected_difference: str = "rendered models"
