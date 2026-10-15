"""Python CLI entrypoint the native `sqb` executable hands every invocation it does not serve."""

import sys

from sqlbuild._native import LAUNCH_RECORD_OPTION
from sqlbuild.cli.entry.main.entry import main as run_cli


def main() -> int:
    """Run the CLI with the arguments `sqb` received; the CLI reads a leading launch record."""

    arguments: list[str] = sys.argv[1:]
    offered: bool = bool(arguments) and arguments[0].startswith(LAUNCH_RECORD_OPTION)
    sys.argv = [sys.argv[0], *arguments[int(offered) :]]
    return run_cli(arguments)
