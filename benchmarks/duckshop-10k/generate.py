"""Generate the DuckShop 10K project, or check a generated copy against checksum.txt.

python benchmarks/duckshop-10k/generate.py --out /path/to/duckshop-10k
python benchmarks/duckshop-10k/generate.py --check
python benchmarks/duckshop-10k/generate.py --verify /path/to/duckshop-10k
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from duckshop10k.manifest import checksum_line, read_project, write_project  # noqa: E402
from duckshop10k.project import PROFILES, build  # noqa: E402

CHECKSUM_FILE = HERE / "checksum.txt"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--out", type=Path, help="write the project into this new directory")
    action.add_argument(
        "--check", action="store_true", help="generate in memory and compare with checksum.txt"
    )
    action.add_argument(
        "--verify", type=Path, help="compare a generated directory with checksum.txt"
    )
    action.add_argument(
        "--update-checksum", action="store_true", help="rewrite checksum.txt from a fresh build"
    )
    parser.add_argument("--profile", choices=sorted(PROFILES), default="full")
    arguments = parser.parse_args(argv)

    if arguments.verify is not None:
        return _compare(checksum_line(read_project(arguments.verify)))
    files = build(arguments.profile)
    if arguments.out is not None:
        write_project(files, arguments.out)
        print(f"wrote {len(files)} files to {arguments.out}: {checksum_line(files).strip()}")
        return 0
    if arguments.profile != "full":
        parser.error("checksum.txt records the full profile only")
    if arguments.update_checksum:
        CHECKSUM_FILE.write_text(checksum_line(files))
        print(checksum_line(files).strip())
        return 0
    return _compare(checksum_line(files))


def _compare(actual: str) -> int:
    expected = CHECKSUM_FILE.read_text()
    if actual != expected:
        print(f"checksum mismatch\n  expected: {expected.strip()}\n  actual:   {actual.strip()}")
        return 1
    print(f"checksum matches: {actual.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
