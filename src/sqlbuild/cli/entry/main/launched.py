"""Python CLI entrypoint the native `sqb` executable hands every invocation it does not serve."""

import sys
from pathlib import Path

from sqlbuild.cli.entry._helpers.launch_state import offer_launch_record
from sqlbuild.cli.entry.constants import LAUNCH_RECORD_OPTION
from sqlbuild.cli.entry.main.entry import main as run_cli


def main() -> int:
    """Run the CLI with the arguments `sqb` received, remembering where its launch record goes."""

    arguments: list[str] = sys.argv[1:]
    if arguments and arguments[0].startswith(LAUNCH_RECORD_OPTION):
        _ = offer_launch_record(Path(arguments[0].removeprefix(LAUNCH_RECORD_OPTION)))
        arguments = arguments[1:]
    sys.argv = [sys.argv[0], *arguments]
    return run_cli()
