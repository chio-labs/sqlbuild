"""SQLBuild argument parser behavior."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from sqlbuild.presentation.classes.cli_style import CliStyle


class SqlbuildArgumentParser(argparse.ArgumentParser):
    """Argument parser that renders parser failures with a stable code."""

    use_color: bool = False

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        style: CliStyle = CliStyle(use_color=self.use_color)
        prefix: str = style.error_strong("error[C900]:")
        self.exit(2, f"{self.prog}: {prefix} {message}\n\n")
