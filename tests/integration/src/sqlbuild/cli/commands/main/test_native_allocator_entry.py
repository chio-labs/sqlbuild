"""Fresh-process integration coverage for the native allocator entrypoint default."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    NativeAllocatorEntryTestCase,
)

_PURGE_DELAY_VARIABLE: str = "MIMALLOC_PURGE_DELAY"
_SCRIPT: str = """
import json
import os
import sys
from sqlbuild.cli.entry.main.entry import main

loaded_at_import = "sqlbuild._native" in sys.modules
exit_code = main(["--version"])
loaded_by_version = "sqlbuild._native" in sys.modules
import sqlbuild._native
print(json.dumps({
    "loaded_at_import": loaded_at_import,
    "loaded_by_version": loaded_by_version,
    "purge_delay": os.environ.get("MIMALLOC_PURGE_DELAY"),
    "exit_code": exit_code,
}))
"""


@pytest.mark.parametrize(
    "test_case",
    [
        NativeAllocatorEntryTestCase(
            description="unset purge delay defaults to ten milliseconds",
            inherited_environment=(),
            expected_purge_delay="10",
        ),
        NativeAllocatorEntryTestCase(
            description="user purge delay is preserved",
            inherited_environment=((_PURGE_DELAY_VARIABLE, "250"),),
            expected_purge_delay="250",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fresh_process_when_running_cli_entry_then_purge_delay_is_set_before_native_load(
    test_case: NativeAllocatorEntryTestCase,
) -> None:
    environment: dict[str, str] = os.environ.copy()
    environment.pop(_PURGE_DELAY_VARIABLE, None)
    environment.update(test_case.inherited_environment)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )
    payload: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])

    assert payload == {
        "loaded_at_import": False,
        "loaded_by_version": False,
        "purge_delay": test_case.expected_purge_delay,
        "exit_code": 0,
    }


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
