"""Generated docs reference output handling."""

from pathlib import Path

from scripts.docs_skill.constants import GENERATED_MARKER


def write_reference_pages(*, output_dir: Path, pages: dict[str, str]) -> None:
    """Write generated reference pages and remove stale generated pages."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for relative_path, contents in pages.items():
        destination: Path = output_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(contents, encoding="utf-8")
    stale_paths: list[Path] = [
        path
        for path in output_dir.rglob("*.md")
        if path.relative_to(output_dir).as_posix() not in pages
        and GENERATED_MARKER in path.read_text(encoding="utf-8")
    ]
    for stale_path in stale_paths:
        stale_path.unlink()
    for directory in sorted(output_dir.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    print(f"Wrote {len(pages)} reference pages to {output_dir} ({len(stale_paths)} removed)")
