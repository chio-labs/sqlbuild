"""Direct wrapper for SQLBuild docs skill generation."""

from __future__ import annotations

from scripts.docs_skill.main.generate import generate_docs_skill


def main(argv: list[str] | None = None) -> int:
    """Generate the SQLBuild documentation skill."""

    return generate_docs_skill(argv)


if __name__ == "__main__":
    raise SystemExit(main())
