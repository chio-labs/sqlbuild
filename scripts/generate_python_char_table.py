"""Direct wrapper for regenerating the native `str.isalnum()` table; run it with the CI Python."""

from __future__ import annotations

from scripts.python_char_table.main.generate import generate_python_char_table


def main() -> int:
    """Regenerate the native Python character table."""

    return generate_python_char_table()


if __name__ == "__main__":
    raise SystemExit(main())
