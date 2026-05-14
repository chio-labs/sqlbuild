"""Generate a Markdown SKILL.md from the SQLBuild docs repo."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

default_repo_url = "https://github.com/chio-labs/sqlbuild-docs"
default_clone_dir = Path(tempfile.gettempdir()) / "sqlbuild-docs-skill-source"
default_output_path = Path("src/sqlbuild/.agents/skills/sqlbuild/SKILL.md")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    docs_root = args.docs_root
    if docs_root is None:
        docs_root = clone_docs_repo(repo_url=args.repo_url, clone_dir=args.clone_dir)

    skill_markdown = build_skill_markdown(
        docs_root=docs_root,
        include_introduction=not args.exclude_introduction,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(skill_markdown, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


def clone_docs_repo(*, repo_url: str, clone_dir: Path) -> Path:
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(clone_dir)],
        check=True,
    )
    return clone_dir


def build_skill_markdown(*, docs_root: Path, include_introduction: bool = True) -> str:
    page_paths = list_ordered_page_paths(docs_root=docs_root)
    if not include_introduction:
        page_paths = [path for path in page_paths if path.with_suffix("").as_posix() != "index"]

    sections = [_render_skill_header(page_paths=page_paths)]
    for page_path in page_paths:
        absolute_path = docs_root / page_path
        page = _parse_mdx_page(absolute_path.read_text(encoding="utf-8"))
        sections.append(_render_page_section(page=page, source_path=page_path))

    return _normalize_blank_lines("\n\n".join(sections)).strip() + "\n"


def list_ordered_page_paths(*, docs_root: Path) -> list[Path]:
    docs_json_path = docs_root / "docs.json"
    if docs_json_path.exists():
        docs_json = json.loads(docs_json_path.read_text(encoding="utf-8"))
        ordered_pages = _collect_navigation_pages(docs_json.get("navigation", {}))
    else:
        ordered_pages = sorted(path.with_suffix("").as_posix() for path in docs_root.rglob("*.mdx"))

    page_paths: list[Path] = []
    seen_pages: set[str] = set()
    for page in ordered_pages:
        page_path = Path(f"{page}.mdx")
        if page in seen_pages or not (docs_root / page_path).exists():
            continue
        page_paths.append(page_path)
        seen_pages.add(page)

    for mdx_path in sorted(docs_root.rglob("*.mdx")):
        page = mdx_path.relative_to(docs_root).with_suffix("").as_posix()
        if page not in seen_pages:
            page_paths.append(mdx_path.relative_to(docs_root))
            seen_pages.add(page)

    return page_paths


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone sqlbuild-docs and convert all MDX pages into a single SKILL.md."
    )
    parser.add_argument("--repo-url", default=default_repo_url)
    parser.add_argument("--clone-dir", type=Path, default=default_clone_dir)
    parser.add_argument("--docs-root", type=Path)
    parser.add_argument("--output", type=Path, default=default_output_path)
    parser.add_argument("--exclude-introduction", action="store_true")
    return parser.parse_args(argv)


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


def _parse_mdx_page(contents: str) -> dict[str, str]:
    frontmatter, body = _split_frontmatter(contents)
    title = frontmatter.get("title") or "Untitled"
    description = frontmatter.get("description", "")
    return {
        "title": title,
        "description": description,
        "body": _clean_mdx_body(body),
    }


def _split_frontmatter(contents: str) -> tuple[dict[str, str], str]:
    lines = contents.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, contents

    frontmatter: dict[str, str] = {}
    end_index = 0
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
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
    in_code_block = False

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            cleaned_lines.append(line)
            continue
        if in_code_block:
            cleaned_lines.append(line)
            continue

        stripped = line.strip()
        if _is_mdx_only_line(stripped):
            continue
        cleaned_lines.append(_shift_markdown_heading(line))

    return _normalize_blank_lines("\n".join(cleaned_lines)).strip()


def _is_mdx_only_line(stripped: str) -> bool:
    if not stripped:
        return False
    if stripped.startswith(("import ", "export ")):
        return True
    if re.fullmatch(r"</?[A-Z][^>]*>", stripped):
        return True
    if re.fullmatch(r"<[A-Z][^>]*/>", stripped):
        return True
    if re.fullmatch(r"<img\s+[^>]*/>", stripped):
        return True
    return False


def _shift_markdown_heading(line: str) -> str:
    if re.match(r"^#{1,6} ", line):
        return f"#{line}"
    return line


def _render_skill_header(*, page_paths: list[Path]) -> str:
    page_list = "\n".join(f"- `{path.with_suffix('').as_posix()}`" for path in page_paths)
    return (
        "# SQLBuild Skill\n\n"
        "This file is generated from the SQLBuild documentation. Use it as the source of truth "
        "for SQLBuild syntax, project structure, configuration, testing, adapters, and CLI "
        f"behavior.\n\n## Included Pages\n\n{page_list}"
    )


def _render_page_section(*, page: dict[str, str], source_path: Path) -> str:
    description = page["description"]
    description_block = f"\n\n{description}" if description else ""
    body_block = f"\n\n{page['body']}" if page["body"] else ""
    return f"""## {page["title"]}

Source: `{source_path.as_posix()}`{description_block}{body_block}"""


def _normalize_blank_lines(contents: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", contents)


if __name__ == "__main__":
    raise SystemExit(main())
