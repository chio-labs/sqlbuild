"""Test case types for native compiled project integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetainedRulesRowsTestCase:
    """A real compile whose rules request reads model facts the compile-input stage retained."""

    description: str
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class UnretainedRulesRowsTestCase:
    """A compile whose model facts were not retained, so rules cannot read them."""

    description: str
    expected_error: str


@dataclass(frozen=True)
class ZeroMaterializationTestCase:
    """An ordinary compile that must not construct the legacy Python project representation."""

    description: str
    arguments: tuple[str, ...]
    expected_constructions: dict[str, int]


@dataclass(frozen=True)
class ModelLoopParityTestCase:
    """A project whose model inputs the native loop builds as the attachment recorded them."""

    description: str
    fixtures: tuple[str, ...]
    files: dict[str, str]
    expected_native_models: int
    expected_summary: str


@dataclass(frozen=True)
class ModelLoopErrorTestCase:
    """A model the native loop rejects with the attachment's exact message and code."""

    description: str
    model_sql: str
    expected_message: str
    expected_code: str
    files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelPathScopeErrorTestCase:
    """A model path the scope lookup rejects while the loop resolves its declarations."""

    description: str
    model_path: str
    expected_message: str
    expected_code: str


@dataclass(frozen=True)
class ImmediateSyntaxErrorTestCase:
    """A model the native loop rejects while validating its SQL syntax immediately."""

    description: str
    model_sql: str
    expected_message: str
    expected_help_fragment: str
