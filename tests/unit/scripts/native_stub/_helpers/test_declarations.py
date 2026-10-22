import pytest

from scripts.native_stub._helpers.declarations import stub_drift
from tests.unit.scripts.native_stub._helpers._test_types import NativeStubDriftTestCase

STUB: str = (
    "from typing import Protocol, TypedDict\n"
    "\n"
    "type Row = tuple[str, int]\n"
    "API_VERSION: int\n"
    "\n"
    "class Handler(Protocol):\n"
    "    def __call__(self) -> int: ...\n"
    "\n"
    "class Request(TypedDict):\n"
    "    name: str\n"
    "\n"
    "class _Storage:\n"
    "    def path(self) -> str: ...\n"
    "\n"
    "class History(_Storage): ...\n"
    "\n"
    "def digest(text: str) -> str: ...\n"
    "def _hook() -> None: ...\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeStubDriftTestCase(
            description="every runtime declaration is registered",
            stub_text=STUB,
            registered=frozenset({"API_VERSION", "History", "digest", "_hook"}),
            expected_drift=(),
        ),
        NativeStubDriftTestCase(
            description="unregistered functions, classes and constants are reported",
            stub_text=STUB,
            registered=frozenset({"History"}),
            expected_drift=("API_VERSION", "_hook", "digest"),
        ),
        NativeStubDriftTestCase(
            description="unregistered class is reported",
            stub_text=STUB,
            registered=frozenset({"API_VERSION", "digest", "_hook"}),
            expected_drift=("History",),
        ),
        NativeStubDriftTestCase(
            description="protocols, typed dicts, aliases and private classes need no registration",
            stub_text=STUB,
            registered=frozenset({"API_VERSION", "History", "digest", "_hook", "Unrelated"}),
            expected_drift=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_stub_when_comparing_registered_names_then_reports_unregistered_declarations(
    test_case: NativeStubDriftTestCase,
) -> None:
    drift: tuple[str, ...] = stub_drift(
        stub_text=test_case.stub_text, registered=test_case.registered
    )

    assert drift == test_case.expected_drift
