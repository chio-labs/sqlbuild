"""Markdown rendering for bundled SQLBuild docs reference pages."""

import os
import re
from pathlib import Path, PurePosixPath

from scripts.docs_skill._helpers.mdx import normalize_blank_lines, parse_mdx_page
from scripts.docs_skill._helpers.navigation import list_navigation_groups
from scripts.docs_skill.constants import (
    DOCS_BASE_URL,
    GENERATED_MARKER,
    INDEX_FILENAME,
    TABLE_OF_CONTENTS_MIN_LINES,
)
from scripts.docs_skill.models import MdxPage, NavigationGroup

_INTERNAL_LINK: re.Pattern[str] = re.compile(r"\]\((/[^)\s#]*)(#[^)\s]*)?\)")
_SECTION_HEADING: re.Pattern[str] = re.compile(r"^## (.+)$", re.MULTILINE)


def build_reference_pages(*, docs_root: Path) -> dict[str, str]:
    """Render every documentation page plus a grouped index, keyed by relative output path."""

    groups: list[NavigationGroup] = list_navigation_groups(docs_root=docs_root)
    page_names: set[str] = set()
    for group in groups:
        page_names.update(path.with_suffix("").as_posix() for path in group.page_paths)
    known_pages: frozenset[str] = frozenset(page_names)
    pages: dict[str, MdxPage] = {}
    rendered: dict[str, str] = {}
    for group in groups:
        for page_path in group.page_paths:
            page_name: str = page_path.with_suffix("").as_posix()
            page: MdxPage = parse_mdx_page((docs_root / page_path).read_text(encoding="utf-8"))
            pages[page_name] = page
            rendered[f"{page_name}.md"] = _render_page(
                page=page, page_name=page_name, known_pages=known_pages
            )
    rendered[INDEX_FILENAME] = _render_index(groups=groups, pages=pages)
    return rendered


def _render_page(*, page: MdxPage, page_name: str, known_pages: frozenset[str]) -> str:
    body: str = _rewrite_internal_links(
        body=page.body, page_name=page_name, known_pages=known_pages
    )
    description_block: str = f"> {page.description}\n\n" if page.description else ""
    contents_block: str = _table_of_contents(body=body)
    return (
        normalize_blank_lines(
            f"{GENERATED_MARKER}\n\n# {page.title}\n\n{description_block}"
            f"Online: {DOCS_BASE_URL}/{page_name}\n\n{contents_block}{body}"
        ).strip()
        + "\n"
    )


def _table_of_contents(*, body: str) -> str:
    if body.count("\n") < TABLE_OF_CONTENTS_MIN_LINES:
        return ""
    headings: list[str] = _SECTION_HEADING.findall(_without_code_blocks(body))
    if not headings:
        return ""
    return "## Contents\n\n" + "".join(f"- {heading}\n" for heading in headings) + "\n"


def _without_code_blocks(body: str) -> str:
    return re.sub(r"```.*?```", "", body, flags=re.DOTALL)


def _rewrite_internal_links(*, body: str, page_name: str, known_pages: frozenset[str]) -> str:
    source_dir: PurePosixPath = PurePosixPath(page_name).parent

    def replace(match: re.Match[str]) -> str:
        target: str = match.group(1).strip("/") or "index"
        anchor: str = match.group(2) or ""
        if target not in known_pages:
            return f"]({DOCS_BASE_URL}/{target}{anchor})"
        relative: str = os.path.relpath(f"{target}.md", start=source_dir.as_posix() or ".")
        return f"]({PurePosixPath(relative).as_posix()}{anchor})"

    return _INTERNAL_LINK.sub(replace, body)


def _render_index(*, groups: list[NavigationGroup], pages: dict[str, MdxPage]) -> str:
    sections: list[str] = []
    for group in groups:
        lines: list[str] = [f"## {group.label}", ""]
        for page_path in group.page_paths:
            page_name: str = page_path.with_suffix("").as_posix()
            page: MdxPage = pages[page_name]
            summary: str = f" - {page.description}" if page.description else ""
            lines.append(f"- [{page.title}]({page_name}.md) (`{page_name}`){summary}")
        sections.append("\n".join(lines))
    return (
        f"{GENERATED_MARKER}\n\n# SQLBuild documentation index\n\n"
        "Bundled copies of every page on the SQLBuild documentation site, matching the "
        "installed SQLBuild version. Open only the page you need.\n\n"
        + "\n\n".join(sections)
        + "\n"
    )
