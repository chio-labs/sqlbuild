"""Generate deterministic agent guidance from the resolved kata policy."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.kata_engine._helpers.guidance.skills import render_skills
from sqlbuild.kata_engine.constants import KATA_SKILL_PATHS
from sqlbuild.kata_engine.models import KataConfig


def install_skills(*, config: KataConfig, project_dir: Path, check: bool) -> bool:
    """Install all owned skill targets or report whether they are fresh."""

    content: str = render_skills(config=config, project_dir=project_dir)
    targets: tuple[Path, ...] = tuple(project_dir / value for value in KATA_SKILL_PATHS)
    fresh: bool = all(
        path.is_file() and path.read_text(encoding="utf-8") == content for path in targets
    )
    if check:
        return fresh
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = path.with_suffix(".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    return True
