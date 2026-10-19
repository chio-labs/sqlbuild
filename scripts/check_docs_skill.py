"""Direct wrapper for the docs skill freshness check."""

from __future__ import annotations

from scripts.docs_skill.main.check import check_docs_skill


def main(argv: list[str] | None = None) -> int:
    """Check that the SQLBuild documentation skill is up to date."""

    return check_docs_skill(argv)


if __name__ == "__main__":
    raise SystemExit(main())
