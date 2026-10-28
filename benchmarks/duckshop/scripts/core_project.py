"""Copy the DuckShop project without its edge-case area, for benchmarks and core measurements.

    python benchmarks/duckshop/scripts/core_project.py <destination>
    python benchmarks/duckshop/scripts/core_project.py --checksum <compiled project>

The edge-case area holds hand-picked edge values, not benchmark workload, so compile benchmarks
measure this copy. It leaves out every file and folder whose name starts with `edge_`, `_edge_`
or `test_edge_`: the `edge_cases` model, test and scenario folders, their source file, loaders,
Rule and Rule tests, and their scenario snapshots. From `sqlbuild_project.toml` it leaves out the
blocks between `# >>> edge-case area` and `# <<< edge-case area`: the edge connection and target,
the edge variable and the edge Rule ignores. Local-only files such as `target/` and
`sqlbuild_local.toml` are left out too.

`--checksum` prints the SHA-256 of a compiled project's `target/compiled/` files, the value the
core-copy compile guard compares with. A change to a core model changes it on purpose; record the
new value in the guard and note the change for the benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent / "project"
PROJECT_FILE = "sqlbuild_project.toml"
EDGE_AREA_PATTERNS = ("edge_*", "_edge_*", "test_edge_*")
LOCAL_ONLY_PATTERNS = ("target", "logs", ".sqlbuild", "sqlbuild_local.toml", "__pycache__")
EDGE_BLOCK_START = "# >>> edge-case area"
EDGE_BLOCK_END = "# <<< edge-case area"


def without_edge_blocks(text: str) -> str:
    """The project file without its marked edge-case blocks, markers included."""

    kept: list[str] = []
    inside = False
    for line in text.splitlines(keepends=True):
        if line.startswith(EDGE_BLOCK_START):
            inside = True
        elif line.startswith(EDGE_BLOCK_END):
            inside = False
        elif not inside:
            kept.append(line)
    if inside:
        raise ValueError(f"{PROJECT_FILE}: '{EDGE_BLOCK_START}' has no '{EDGE_BLOCK_END}'")
    text = "".join(kept)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip("\n") + "\n"


def copy_core_project(destination: pathlib.Path) -> None:
    shutil.copytree(
        PROJECT,
        destination,
        ignore=shutil.ignore_patterns(*EDGE_AREA_PATTERNS, *LOCAL_ONLY_PATTERNS),
    )
    project_file = destination / PROJECT_FILE
    project_file.write_text(without_edge_blocks(project_file.read_text()))


def compiled_checksum(project_dir: pathlib.Path) -> str:
    """SHA-256 over every compiled file's relative path and bytes, in path order."""

    compiled = project_dir / "target" / "compiled"
    digest = hashlib.sha256()
    for path in sorted(p for p in compiled.rglob("*") if p.is_file()):
        digest.update(path.relative_to(compiled).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("destination", type=pathlib.Path, help="new folder for the copy")
    parser.add_argument(
        "--checksum",
        action="store_true",
        help="print the checksum of DESTINATION's compiled files instead of copying",
    )
    args = parser.parse_args()
    if args.checksum:
        if not (args.destination / "target" / "compiled").is_dir():
            print(f"{args.destination} has no target/compiled; compile it first", file=sys.stderr)
            return 1
        print(compiled_checksum(args.destination))
        return 0
    if args.destination.exists():
        print(f"{args.destination} already exists", file=sys.stderr)
        return 1
    copy_core_project(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
