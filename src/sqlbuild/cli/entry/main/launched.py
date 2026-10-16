"""Python CLI entrypoint the native `sqb` executable hands every invocation it does not serve."""

import os
import sys

from sqlbuild.cli.entry.constants import (
    NATIVE_ALLOCATOR_PURGE_DELAY_MILLISECONDS,
    NATIVE_ALLOCATOR_PURGE_DELAY_VARIABLE,
)
from sqlbuild.cli.entry.main.entry import main as run_cli


def main() -> int:
    """Run the CLI with the `sqb` arguments, setting the allocator purge delay first."""

    os.environ.setdefault(
        NATIVE_ALLOCATOR_PURGE_DELAY_VARIABLE, NATIVE_ALLOCATOR_PURGE_DELAY_MILLISECONDS
    )
    from sqlbuild._native import LAUNCH_RECORD_OPTION

    arguments: list[str] = sys.argv[1:]
    offered: bool = bool(arguments) and arguments[0].startswith(LAUNCH_RECORD_OPTION)
    sys.argv = [sys.argv[0], *arguments[int(offered) :]]
    return run_cli(arguments)
