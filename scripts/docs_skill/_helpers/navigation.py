"""Documentation navigation discovery for skill generation."""

import json
from pathlib import Path
from typing import Any

from scripts.docs_skill.constants import UNGROUPED_LABEL
from scripts.docs_skill.models import NavigationGroup


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
        for key in ("root", "groups", "pages"):
            pages.extend(_collect_navigation_pages(node.get(key, [])))

    return pages


def list_navigation_groups(*, docs_root: Path) -> list[NavigationGroup]:
    """Return pages grouped by top-level navigation group, then unlisted pages."""

    ordered_paths: list[Path] = list_ordered_page_paths(docs_root=docs_root)
    docs_json_path: Path = docs_root / "docs.json"
    top_level_nodes: list[Any] = []
    if docs_json_path.exists():
        navigation: Any = json.loads(docs_json_path.read_text(encoding="utf-8")).get(
            "navigation", {}
        )
        top_level_nodes = navigation.get("groups", []) if isinstance(navigation, dict) else []

    groups: list[NavigationGroup] = []
    grouped_pages: set[str] = set()
    for node in top_level_nodes:
        label: str = str(node.get("group", UNGROUPED_LABEL)) if isinstance(node, dict) else ""
        member_pages: set[str] = set(_collect_navigation_pages(node))
        page_paths: tuple[Path, ...] = tuple(
            path
            for path in ordered_paths
            if path.with_suffix("").as_posix() in member_pages
            and path.with_suffix("").as_posix() not in grouped_pages
        )
        grouped_pages.update(path.with_suffix("").as_posix() for path in page_paths)
        if page_paths:
            groups.append(NavigationGroup(label=label, page_paths=page_paths))

    remaining: tuple[Path, ...] = tuple(
        path for path in ordered_paths if path.with_suffix("").as_posix() not in grouped_pages
    )
    if remaining:
        groups.append(NavigationGroup(label=UNGROUPED_LABEL, page_paths=remaining))
    return groups
