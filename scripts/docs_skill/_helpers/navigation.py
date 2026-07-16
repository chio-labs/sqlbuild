"""Documentation navigation discovery for skill generation."""

import json
from pathlib import Path
from typing import Any


def list_ordered_page_paths(*, docs_root: Path) -> list[Path]:
    """Return existing MDX pages in navigation order followed by unlisted pages."""

    docs_json_path: Path = docs_root / "docs.json"
    if docs_json_path.exists():
        docs_json: dict[str, Any] = json.loads(docs_json_path.read_text(encoding="utf-8"))
        ordered_pages: list[str] = _collect_navigation_pages(docs_json.get("navigation", {}))
    else:
        ordered_pages = sorted(path.with_suffix("").as_posix() for path in docs_root.rglob("*.mdx"))

    page_paths: list[Path] = []
    seen_pages: set[str] = set()
    for page in ordered_pages:
        page_path: Path = Path(f"{page}.mdx")
        if page in seen_pages or not (docs_root / page_path).exists():
            continue
        page_paths.append(page_path)
        seen_pages.add(page)

    for mdx_path in sorted(docs_root.rglob("*.mdx")):
        page: str = mdx_path.relative_to(docs_root).with_suffix("").as_posix()
        if page not in seen_pages:
            page_paths.append(mdx_path.relative_to(docs_root))
            seen_pages.add(page)

    return page_paths


def _collect_navigation_pages(node: Any) -> list[str]:
    pages: list[str] = []

    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        for item in node:
            pages.extend(_collect_navigation_pages(item))
        return pages
    if isinstance(node, dict):
        for key in ("groups", "pages"):
            pages.extend(_collect_navigation_pages(node.get(key, [])))

    return pages
