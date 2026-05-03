"""CLI entrypoint for structure convention checks."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root: Path = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def main(argv: list[str] | None = None) -> int:
    """Run the structure convention checker CLI."""

    from scripts.structure.structure_conventions.checker import main as checker_main

    return checker_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
