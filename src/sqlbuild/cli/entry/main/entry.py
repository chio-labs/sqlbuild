"""Public SQLBuild CLI process entrypoint."""

from collections.abc import Sequence

from sqlbuild.cli.commands.main.entrypoint.entry import main as _main


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SQLBuild CLI with optional explicit arguments."""

    return _main(argv)
