"""Public SQLBuild CLI process entrypoint."""

import os
from collections.abc import Sequence

from sqlbuild.cli.entry.constants import (
    NATIVE_ALLOCATOR_PURGE_DELAY_MILLISECONDS,
    NATIVE_ALLOCATOR_PURGE_DELAY_VARIABLE,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SQLBuild CLI with optional explicit arguments."""

    os.environ.setdefault(
        NATIVE_ALLOCATOR_PURGE_DELAY_VARIABLE, NATIVE_ALLOCATOR_PURGE_DELAY_MILLISECONDS
    )
    from sqlbuild.cli.commands.main.entrypoint.entry import main as run_cli

    return run_cli(argv)
