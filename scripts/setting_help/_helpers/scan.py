"""Source scanning for setting names in authored diagnostic text."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.setting_help.constants import (
    DOTTED_SETTING_INSTRUCTION_PATTERN,
    RUST_STRING_DELIMITER,
    RUST_TEST_PATH_MARKER,
    YAML_FILE_TEXT_MODULES,
    YAML_STYLE_SETTING_PATTERN,
)


def python_findings(repository_root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted((repository_root / "src" / "sqlbuild").rglob("*.py")):
        relative: str = path.relative_to(repository_root).as_posix()
        if relative in YAML_FILE_TEXT_MODULES:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant | ast.JoinedStr):
                text: str = _literal_text(node)
                if names_setting_without_snippet(text):
                    findings.append(f"{relative}:{node.lineno}: {text}")
    return findings


def rust_findings(repository_root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted((repository_root / "crates").rglob("src/**/*.rs")):
        relative: str = path.relative_to(repository_root).as_posix()
        if RUST_TEST_PATH_MARKER in relative:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if RUST_STRING_DELIMITER in line and names_setting_without_snippet(line):
                findings.append(f"{relative}:{number}: {line.strip()}")
    return findings


def names_setting_without_snippet(text: str) -> bool:
    return bool(
        YAML_STYLE_SETTING_PATTERN.search(text) or DOTTED_SETTING_INSTRUCTION_PATTERN.search(text)
    )


def _literal_text(node: ast.Constant | ast.JoinedStr) -> str:
    parts: list[ast.expr] = list(node.values) if isinstance(node, ast.JoinedStr) else [node]
    return "".join(
        part.value
        for part in parts
        if isinstance(part, ast.Constant) and isinstance(part.value, str)
    )
