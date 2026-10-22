"""Native stub check command entrypoint."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from scripts.native_stub._helpers.declarations import stub_drift
from scripts.native_stub.constants import NATIVE_MODULE, STUB_PATH


def run_native_stub_check(argv: list[str] | None = None) -> int:
    """Fail when the stub declares a runtime name the built native extension does not register."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments: argparse.Namespace = parser.parse_args(argv)
    registered: frozenset[str] = frozenset(dir(importlib.import_module(NATIVE_MODULE)))
    stub_text: str = (arguments.root / STUB_PATH).read_text(encoding="utf-8")
    missing: tuple[str, ...] = stub_drift(stub_text=stub_text, registered=registered)
    if missing:
        print(f"{STUB_PATH} declares names {NATIVE_MODULE} does not register:", file=sys.stderr)
        for name in missing:
            print(f"- {name}", file=sys.stderr)
        return 1
    print(f"{STUB_PATH} declares only registered names.")
    return 0
