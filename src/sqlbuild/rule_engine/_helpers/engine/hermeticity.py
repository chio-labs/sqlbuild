"""Static import verification for the fingerprinted custom-rule source closure."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlbuild.rule_engine._helpers.engine.custom_rule_evidence import custom_rule_import_closure
from sqlbuild.rule_engine.constants import CUSTOM_RULE_IMPORT_ROOTS
from sqlbuild.rule_engine.exceptions import NonHermeticRuleError, RulesError
from sqlbuild.rule_engine.models import Rule


def verify_custom_rules(*, rules: tuple[Rule, ...], project_dir: Path) -> None:
    """Reject imports outside the deterministic allowlist in every fingerprinted rule file."""

    root: Path = project_dir.resolve()
    checked: set[Path] = set()
    for rule in rules:
        if not rule.custom or rule.source is None:
            continue
        source_path: Path = Path(rule.source).resolve()
        closure: tuple[Path, ...] = custom_rule_import_closure(rule=rule, project_dir=root)
        for path in (source_path, *closure):
            if path in checked:
                continue
            checked.add(path)
            _verify_source(path=path, project_dir=root)


def allowed_custom_rule_import(module: str) -> bool:
    """Return whether custom-rule code may import one absolute module name."""

    return any(module == root or module.startswith(f"{root}.") for root in CUSTOM_RULE_IMPORT_ROOTS)


def _verify_source(*, path: Path, project_dir: Path) -> None:
    if not path.is_relative_to(project_dir):
        raise RulesError(f"custom rule source must be repository-owned: {path}")
    source: str = path.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _verify_import(path=path, line=node.lineno, module=alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            _verify_import(path=path, line=node.lineno, module=node.module or "")


def _verify_import(*, path: Path, line: int, module: str) -> None:
    if not allowed_custom_rule_import(module):
        raise NonHermeticRuleError(
            f"non-hermetic custom rule at {path}:{line}: import {module!r} is not allowed"
        )
