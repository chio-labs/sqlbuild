"""Describe catalogued custom rules, reading their user functions, for native selection."""

from __future__ import annotations

import inspect
from pathlib import Path

from sqlbuild._native import (
    Rule,
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
    custom_rule_test_evidence,
)


def custom_rule_payloads(
    *, catalogue: tuple[Rule, ...], project_dir: Path
) -> list[dict[str, object]]:
    """Describe every catalogued custom rule for native selection and evaluation."""

    closures: dict[str, tuple[Path, ...]] = {}
    return [
        _custom_rule_payload(
            rule=rule,
            project_dir=project_dir,
            import_closure=_shared_import_closure(
                rule=rule, project_dir=project_dir, cache=closures
            ),
        )
        for rule in catalogue
        if rule.custom
    ]


def _custom_rule_payload(
    *, rule: Rule, project_dir: Path, import_closure: tuple[Path, ...]
) -> dict[str, object]:
    return {
        "code": rule.code,
        "family": rule.family,
        "slug": rule.slug,
        "message": rule.message,
        "remediation": rule.remediation,
        "enabled_by_default": rule.enabled_by_default,
        "implementation_fingerprint": custom_rule_implementation_fingerprint(
            rule=rule, project_dir=project_dir, import_closure=import_closure
        ),
        **_custom_rule_source_payload(rule=rule, project_dir=project_dir),
        "project_wide": rule.project_wide,
        "check_name": getattr(rule.check, "__name__", ""),
        "test_case_count": len(custom_rule_test_evidence(rule=rule, project_dir=project_dir)),
    }


def _shared_import_closure(
    *, rule: Rule, project_dir: Path, cache: dict[str, tuple[Path, ...]]
) -> tuple[Path, ...]:
    if rule.source is None:
        return ()
    source: str = str(Path(rule.source).resolve())
    if source not in cache:
        cache[source] = custom_rule_import_closure(rule=rule, project_dir=project_dir)
    return cache[source]


def _custom_rule_source_payload(*, rule: Rule, project_dir: Path) -> dict[str, object]:
    source: str | None = rule.source
    if source is not None:
        source_path: Path = Path(source).resolve()
        root: Path = project_dir.resolve()
        if source_path.is_relative_to(root):
            source = source_path.relative_to(root).as_posix()
    try:
        source_line: int = inspect.getsourcelines(rule.check)[1]
    except (OSError, TypeError):
        source_line = 1
    check_owner: str = getattr(rule.check, "__qualname__", getattr(rule.check, "__name__", ""))
    return {
        "source": source,
        "source_line": source_line,
        "source_column": 1,
        "owner": f"{source or 'rules'}:{check_owner}",
    }
