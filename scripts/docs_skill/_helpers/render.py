"""Markdown rendering for SQLBuild docs skills."""

from pathlib import Path

from scripts.docs_skill._helpers.mdx import normalize_blank_lines, parse_mdx_page
from scripts.docs_skill._helpers.navigation import list_ordered_page_paths
from scripts.docs_skill.constants import (
    GENERATED_MARKER,
    INTRODUCTION_PAGE_NAME,
    SKILL_FRONTMATTER,
)
from scripts.docs_skill.models import MdxPage


def build_skill_markdown(*, docs_root: Path, include_introduction: bool = True) -> str:
    """Build one Markdown skill from all ordered documentation pages."""

    page_paths: list[Path] = list_ordered_page_paths(docs_root=docs_root)
    if not include_introduction:
        page_paths = [
            path for path in page_paths if path.with_suffix("").as_posix() != INTRODUCTION_PAGE_NAME
        ]

    sections: list[str] = [_render_skill_header(page_paths=page_paths)]
    for page_path in page_paths:
        absolute_path: Path = docs_root / page_path
        page: MdxPage = parse_mdx_page(absolute_path.read_text(encoding="utf-8"))
        sections.append(_render_page_section(page=page, source_path=page_path))

    return normalize_blank_lines("\n\n".join(sections)).strip() + "\n"


def _render_skill_header(*, page_paths: list[Path]) -> str:
    page_list: str = "\n".join(f"- `{path.with_suffix('').as_posix()}`" for path in page_paths)
    return (
        f"{SKILL_FRONTMATTER}\n\n"
        f"{GENERATED_MARKER}\n\n"
        "# SQLBuild Skill\n\n"
        "This file is generated from the SQLBuild documentation. Use it as the source of truth "
        "for SQLBuild syntax, project structure, configuration, testing, adapters, and CLI "
        f"behavior.\n\n## Included Pages\n\n{page_list}"
    )


def _render_page_section(*, page: MdxPage, source_path: Path) -> str:
    description_block: str = f"\n\n{page.description}" if page.description else ""
    body_block: str = f"\n\n{page.body}" if page.body else ""
    return f"""## {page.title}

Source: `{source_path.as_posix()}`{description_block}{body_block}"""
