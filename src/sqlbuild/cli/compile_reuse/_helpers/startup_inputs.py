"""Interpreter and site-path inputs that must remain unchanged before skipping Python startup."""

import site
import sys

from sqlbuild._native import startup_input_stamps


def startup_inputs() -> list[tuple[str, int | None, int | None]]:
    """Stamp startup directories, path files, interpreter and virtual-environment configuration."""

    return startup_input_stamps(
        directories=(*sys.path, *site.getsitepackages(), site.getusersitepackages()),
        files=(sys.executable,),
        prefixes=(sys.prefix, sys.base_prefix),
    )
