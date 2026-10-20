"""`sqlbuild._native_host` agrees with the native host table and imports its targets lazily."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import sqlbuild._native as native
import sqlbuild._native_host as native_host
from scripts.native_module_paths._helpers.host_roots import host_dead_code_roots, host_targets
from tests.unit.scripts.native_module_paths._helpers._test_types import (
    HostDeadCodeRootCase,
    HostImportCase,
    HostKindCase,
    HostTableCase,
    HostUnknownNameCase,
)
from tests.unit.scripts.native_module_paths._helpers.helpers import FENSU_CONFIG, resolved_kind


@pytest.mark.parametrize(
    "test_case",
    [
        HostTableCase(
            description="host names equal the native table",
            expected_duplicate_count=0,
            expected_missing_names=(),
            expected_extra_names=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_native_host_table_when_comparing_names_then_python_and_rust_agree(
    test_case: HostTableCase,
) -> None:
    listed: list[str] = [name for name, _, _ in native.HOST_ENTRIES]
    native_names: set[str] = set(listed)
    host_names: set[str] = set(native_host.host_targets())

    assert len(listed) - len(native_names) == test_case.expected_duplicate_count
    assert tuple(sorted(native_names - host_names)) == test_case.expected_missing_names
    assert tuple(sorted(host_names - native_names)) == test_case.expected_extra_names


@pytest.mark.parametrize(
    "test_case",
    [
        HostKindCase(
            description="every entry resolves to its declared kind", expected_mismatched_names=()
        )
    ],
    ids=lambda case: case.description,
)
def test_given_native_host_table_when_resolving_entries_then_each_has_its_declared_kind(
    test_case: HostKindCase,
) -> None:
    declared: dict[str, str] = {name: kind for name, kind, _ in native.HOST_ENTRIES}
    resolved: dict[str, str] = {
        name: resolved_kind(getattr(native_host, name)) for name in declared
    }

    mismatched: set[tuple[str, str]] = set(resolved.items()) ^ set(declared.items())

    assert tuple(sorted({name for name, _ in mismatched})) == test_case.expected_mismatched_names


@pytest.mark.parametrize(
    "test_case",
    [
        HostImportCase(
            description="importing the host module loads none of its targets",
            expected_loaded_modules=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clean_interpreter_when_importing_native_host_then_no_target_module_loads(
    test_case: HostImportCase,
) -> None:
    script: str = (
        "import json, sys\n"
        "import sqlbuild\n"
        "before = set(sys.modules)\n"
        "import sqlbuild._native_host as host\n"
        "targets = {module for module, _ in host.host_targets().values()}\n"
        "loaded = sorted(targets & (set(sys.modules) - before))\n"
        "print(json.dumps(loaded))\n"
    )

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    )

    assert tuple(json.loads(result.stdout)) == test_case.expected_loaded_modules


@pytest.mark.parametrize(
    "test_case",
    [
        HostUnknownNameCase(
            description="a name outside the table is not an attribute",
            name="no_such_entry",
            expected_error="module 'sqlbuild._native_host' has no attribute 'no_such_entry'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_name_when_reading_native_host_then_raises_attribute_error(
    test_case: HostUnknownNameCase,
) -> None:
    with pytest.raises(AttributeError) as raised:
        getattr(native_host, test_case.name)

    assert str(raised.value) == test_case.expected_error


@pytest.mark.parametrize(
    "test_case",
    [
        HostDeadCodeRootCase(
            description="every host target is a dead-code root and every host root a target",
            expected_missing_targets=(),
            expected_extra_targets=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_native_host_table_when_reading_fensu_roots_then_roots_match_targets(
    test_case: HostDeadCodeRootCase,
) -> None:
    targets: set[tuple[str, str]] = host_targets()
    roots: set[tuple[str, str]] = host_dead_code_roots(config=FENSU_CONFIG)

    assert tuple(sorted(targets - roots)) == test_case.expected_missing_targets
    assert tuple(sorted(roots - targets)) == test_case.expected_extra_targets


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
