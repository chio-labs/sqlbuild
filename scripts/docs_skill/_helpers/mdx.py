"""MDX parsing and cleanup for skill generation."""

import re

from scripts.docs_skill.constants import FRONTMATTER_DELIMITER
from scripts.docs_skill.models import MdxPage


def parse_mdx_page(contents: str) -> MdxPage:
    """Parse frontmatter and Markdown-compatible content from one MDX page."""

    frontmatter, body = _split_frontmatter(contents)
    return MdxPage(
        title=frontmatter.get("title") or "Untitled",
        description=frontmatter.get("description", ""),
        body=_clean_mdx_body(body),
    )


def _split_frontmatter(contents: str) -> tuple[dict[str, str], str]:
    lines: list[str] = contents.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, contents

    frontmatter: dict[str, str] = {}
    end_index: int = 0
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            end_index = index
            break
        key, separator, value = line.partition(":")
        if separator:
            frontmatter[key.strip()] = value.strip().strip('"')

    if end_index == 0:
        return {}, contents

    return frontmatter, "\n".join(lines[end_index + 1 :])


def _clean_mdx_body(body: str) -> str:
    cleaned_lines: list[str] = []
    in_code_block: bool = False

    for raw_line in body.splitlines():
        line: str = raw_line.rstrip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            cleaned_lines.append(line)
            continue
        if in_code_block:
            cleaned_lines.append(line)
            continue

        stripped: str = line.strip()
        if _is_mdx_only_line(stripped):
            continue
        cleaned_lines.append(_shift_markdown_heading(line))

    return normalize_blank_lines("\n".join(cleaned_lines)).strip()


def _is_mdx_only_line(stripped: str) -> bool:
    if not stripped:
        return False
    if stripped.startswith(("import ", "export ")):
        return True
    if re.fullmatch(r"</?[A-Z][^>]*>", stripped):
        return True
    if re.fullmatch(r"<[A-Z][^>]*/>", stripped):
        return True
    return bool(re.fullmatch(r"<img\s+[^>]*/>", stripped))


def _shift_markdown_heading(line: str) -> str:
    if re.match(r"^#{1,6} ", line):
        return f"#{line}"
    return line


def normalize_blank_lines(contents: str) -> str:
    """Collapse runs of blank lines to one blank line."""

    return re.sub(r"\n{3,}", "\n\n", contents)
