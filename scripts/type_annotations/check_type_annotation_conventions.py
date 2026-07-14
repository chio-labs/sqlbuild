"""CLI entrypoint for type annotation convention checks."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root: Path = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def main(argv: list[str] | None = None) -> int:
    """Run the type annotation convention checker CLI."""

    from scripts.type_annotations.type_annotation_conventions.main.check_conventions import (
        check_type_annotation_conventions,
    )

    return check_type_annotation_conventions(argv)


if __name__ == "__main__":
    raise SystemExit(main())
