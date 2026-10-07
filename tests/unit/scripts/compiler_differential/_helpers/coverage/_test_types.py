"""Test case types for discovery coverage classification."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


@dataclass(frozen=True)
class DiscoveryKindsTestCase:
    """One discovery capture fragment and the input kinds it must prove."""

    description: str
    capture: dict[str, object]
    expected_present: frozenset[str]
    expected_absent: frozenset[str]


@dataclass(frozen=True)
class AuthoredByteKindsTestCase:
    """Authored files, the paths discovery read, and whether CRLF must be credited."""

    description: str
    files: dict[str, bytes]
    read_paths: tuple[str, ...]
    expected_crlf: bool


@dataclass(frozen=True)
class RequiredKindsTestCase:
    """Collections that must be required because discovery produces them."""

    description: str
    expected_required: frozenset[str]


@dataclass(frozen=True)
class CaptureProblemsTestCase:
    """A discovery capture and the problems that make it incomplete or not canonical."""

    description: str
    capture: dict[str, object]
    expected_problem_count: int


@dataclass(frozen=True)
class EncodedInputsKindsTestCase:
    """Real discovered inputs, encoded by the stage capture, and the kinds they prove."""

    description: str
    inputs: DiscoveredProjectInputs
    expected_kinds: frozenset[str]
