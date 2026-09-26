"""Documentation navigation discovery for skill generation."""

import json
from pathlib import Path
from typing import Any

from scripts.docs_skill.constants import DOCS_SLUG, INDEX_PAGE, UNGROUPED_LABEL
from scripts.docs_skill.models import NavigationGroup


def list_ordered_page_paths(*, docs_root: Path, sidebar_path: Path | None = None) -> list[Path]:
    """Return existing pages in sidebar order followed by unlisted pages."""

    paths: list[Path] = []
    for group in list_navigation_groups(docs_root=docs_root, sidebar_path=sidebar_path):
        paths.extend(group.page_paths)
    return paths


def _collect_navigation_pages(node: Any) -> list[str]:
    if isinstance(node, str):
        return [INDEX_PAGE if node == DOCS_SLUG else node.removeprefix(f"{DOCS_SLUG}/")]
    if isinstance(node, list):
        pages: list[str] = []
        for item in node:
            pages.extend(_collect_navigation_pages(item))
        return pages
    if isinstance(node, dict):
        return _collect_navigation_pages(node.get("slug", node.get("items", [])))
    return []


def list_navigation_groups(
    *, docs_root: Path, sidebar_path: Path | None = None
) -> list[NavigationGroup]:
    """Flatten nested sidebar groups within each top-level group, then add unlisted pages."""

    sidebar_path = sidebar_path or docs_root.resolve().parents[2] / "sidebar.json"
    nodes: list[Any] = (
        json.loads(sidebar_path.read_text(encoding="utf-8")) if sidebar_path.exists() else []
    )
    available: dict[str, Path] = {}
    for suffix in ("*.md", "*.mdx"):
        for path in sorted(docs_root.rglob(suffix)):
            relative_path: Path = path.relative_to(docs_root)
            available[relative_path.with_suffix("").as_posix()] = relative_path
    groups: list[NavigationGroup] = []
    seen: set[str] = set()
    for node in nodes:
        members: list[Path] = []
        for page in _collect_navigation_pages(node):
            if page in available and page not in seen:
                members.append(available[page])
                seen.add(page)
        if members:
            label: str = (
                node.get("label", UNGROUPED_LABEL) if isinstance(node, dict) else UNGROUPED_LABEL
            )
            groups.append(NavigationGroup(label=label, page_paths=tuple(members)))
    remaining: tuple[Path, ...] = tuple(
        available[page] for page in sorted(available) if page not in seen
    )
    if remaining:
        groups.append(NavigationGroup(label=UNGROUPED_LABEL, page_paths=remaining))
    return groups
