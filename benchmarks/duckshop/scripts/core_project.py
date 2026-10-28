"""Copy the DuckShop project without its edge-case area, for benchmarks and core measurements.

    python benchmarks/duckshop/scripts/core_project.py <destination>

The edge-case area holds hand-picked edge values, not benchmark workload, so compile benchmarks
measure this copy. It leaves out every file and folder whose name starts with `edge_` or `_edge_`:
the `edge_cases` model, test and scenario folders, their source file and loaders, and their
scenario snapshots. Local-only files such as `target/` and `sqlbuild_local.toml` are left out too.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent / "project"
EDGE_AREA_PATTERNS = ("edge_*", "_edge_*")
LOCAL_ONLY_PATTERNS = ("target", "logs", ".sqlbuild", "sqlbuild_local.toml", "__pycache__")


def copy_core_project(destination: pathlib.Path) -> None:
    shutil.copytree(
        PROJECT,
        destination,
        ignore=shutil.ignore_patterns(*EDGE_AREA_PATTERNS, *LOCAL_ONLY_PATTERNS),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("destination", type=pathlib.Path, help="new folder for the copy")
    args = parser.parse_args()
    if args.destination.exists():
        print(f"{args.destination} already exists", file=sys.stderr)
        return 1
    copy_core_project(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
