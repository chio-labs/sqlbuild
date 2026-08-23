"""Generate deterministic agent guidance from the resolved kata policy."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.kata_engine._helpers.engine.native import native_skill_freshness
from sqlbuild.kata_engine._helpers.guidance.skills import render_skills
from sqlbuild.kata_engine.constants import (
    KATA_SKILL_PATHS,
    REPLACEABLE_SKILL_STATES,
    SKILL_FRESH,
)
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataConfig


def install_skills(*, config: KataConfig, project_dir: Path, check: bool) -> bool:
    """Install all owned skill targets or report whether they are fresh."""

    content: str
    input_fingerprint: str
    content, input_fingerprint = render_skills(config=config, project_dir=project_dir)
    targets: tuple[Path, ...] = tuple(project_dir / value for value in KATA_SKILL_PATHS)
    freshness: tuple[str, ...] = tuple(
        native_skill_freshness(
            content=path.read_text(encoding="utf-8") if path.is_file() else None,
            input_fingerprint=input_fingerprint,
        )
        for path in targets
    )
    if check:
        return all(value == SKILL_FRESH for value in freshness)
    for path, state in zip(targets, freshness, strict=True):
        if state not in REPLACEABLE_SKILL_STATES:
            raise KataError(f"refusing to overwrite {state} kata skill: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = path.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    return True
