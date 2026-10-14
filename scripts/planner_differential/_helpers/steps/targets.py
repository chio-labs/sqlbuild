"""Choose the model each step mutates or selects from the previous plan."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.planner_differential._helpers.steps.model_file import split_model_file
from scripts.planner_differential.constants import (
    ADDED_MODEL_NAME,
    ROLE_ANY,
    ROLE_CURSOR,
    ROLE_INCREMENTAL,
    ROLE_LEAF,
    ROLE_MICROBATCH,
    ROLE_TABLE,
)
from scripts.planner_differential.models import ModelFacts

_MATERIALIZATION_TABLE: str = "table"
_MATERIALIZATION_INCREMENTAL: str = "incremental"
_MICROBATCH_MODE: str = "microbatch"
_SQL_SUFFIX: str = ".sql"
_NAME_KEY: str = "name"
_TARGET_DIRECTORY: str = "target"
_SEARCHED_SUFFIXES: frozenset[str] = frozenset({".sql", ".yml", ".yaml", ".py", ".toml"})


def plan_models(plan_json: str) -> tuple[ModelFacts, ...]:
    """Return the models a `sqb plan --json` document lists, or none when it is not JSON."""

    try:
        document: object = json.loads(plan_json)
    except json.JSONDecodeError:
        return ()
    entries: object = document.get("models") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return ()
    return tuple(
        ModelFacts(
            name=str(entry[_NAME_KEY]),
            relative_path=str(entry.get("relative_path") or ""),
            materialization=str(entry.get("materialization_type") or ""),
            qualified_name=str(entry.get("qualified_name") or ""),
            cursor_column=entry.get("cursor_column"),
            microbatch=entry.get("incremental_mode") == _MICROBATCH_MODE,
        )
        for entry in entries
        if isinstance(entry, dict) and _NAME_KEY in entry
    )


def role_target(
    *, role: str, index: int, models: tuple[ModelFacts, ...], project_dir: Path
) -> ModelFacts | None:
    """Return the role's `index`-th candidate (wrapping), or None when it has none."""

    candidates: list[ModelFacts] = sorted(
        (
            model
            for model in models
            if model.name != ADDED_MODEL_NAME
            and _editable(model=model, project_dir=project_dir)
            and _has_role(model=model, role=role, project_dir=project_dir)
        ),
        key=lambda model: model.name,
    )
    return candidates[index % len(candidates)] if candidates else None


def _editable(*, model: ModelFacts, project_dir: Path) -> bool:
    path: Path = project_dir / model.relative_path
    return (
        model.relative_path.endswith(_SQL_SUFFIX)
        and path.is_file()
        and split_model_file(path.read_text(encoding="utf-8")) is not None
    )


def _has_role(*, model: ModelFacts, role: str, project_dir: Path) -> bool:
    if role == ROLE_TABLE:
        return model.materialization == _MATERIALIZATION_TABLE
    if role == ROLE_INCREMENTAL:
        return model.materialization == _MATERIALIZATION_INCREMENTAL
    if role == ROLE_MICROBATCH:
        return model.microbatch
    if role == ROLE_CURSOR:
        return model.cursor_column is not None
    if role == ROLE_LEAF:
        return model.materialization == _MATERIALIZATION_TABLE and not _referenced(
            model=model, project_dir=project_dir
        )
    return role == ROLE_ANY


def _referenced(*, model: ModelFacts, project_dir: Path) -> bool:
    pattern: re.Pattern[str] = re.compile(rf"\b{re.escape(model.name)}\b")
    own: Path = project_dir / model.relative_path
    return any(
        path != own
        and path.suffix in _SEARCHED_SUFFIXES
        and _TARGET_DIRECTORY not in path.relative_to(project_dir).parts
        and pattern.search(path.read_text(encoding="utf-8", errors="replace")) is not None
        for path in sorted(project_dir.rglob("*"))
        if path.is_file()
    )
