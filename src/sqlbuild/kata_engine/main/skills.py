"""Generate deterministic agent guidance from the resolved kata policy."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from tempfile import gettempdir

from filelock import FileLock

from sqlbuild.kata_engine._helpers.engine.native import native_skill_freshness
from sqlbuild.kata_engine._helpers.guidance.skill_installation import install_rendered_skills
from sqlbuild.kata_engine._helpers.guidance.skills import render_skills
from sqlbuild.kata_engine.constants import (
    KATA_SKILL_PATHS,
    SKILL_FRESH,
)
from sqlbuild.kata_engine.models import KataConfig


def install_skills(*, config: KataConfig, project_dir: Path, check: bool) -> bool:
    """Install all owned skill targets or report whether they are fresh."""

    content: str
    input_fingerprint: str
    content, input_fingerprint = render_skills(config=config, project_dir=project_dir)
    targets: tuple[Path, ...] = tuple(project_dir / value for value in KATA_SKILL_PATHS)
    if check:
        return all(
            native_skill_freshness(
                content=path.read_text(encoding="utf-8") if path.is_file() else None,
                input_fingerprint=input_fingerprint,
            )
            == SKILL_FRESH
            for path in targets
        )
    canonical_project: str = os.path.normcase(str(project_dir.resolve()))
    lock_name: str = hashlib.sha256(canonical_project.encode()).hexdigest()
    lock_dir: Path = Path(gettempdir()) / "sqlbuild-kata-skill-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(lock_dir / f"{lock_name}.lock"):
        _ = install_rendered_skills(
            content=content,
            input_fingerprint=input_fingerprint,
            targets=targets,
        )
    return True
