"""Generated skill output handling."""

from pathlib import Path


def write_skill_markdown(*, output_path: Path, contents: str) -> None:
    """Write generated skill Markdown and report its destination."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(contents, encoding="utf-8")
    print(f"Wrote {output_path}")
