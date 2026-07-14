"""Playground command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.cli.commands._helpers.playground.types import PlaygroundTemplate


@dataclass(frozen=True)
class PlaygroundCommandRequest:
    """CLI inputs for one playground command invocation."""

    project_dir: Path | None
    target_path: str
    template: str = PlaygroundTemplate.WAFFLE_SHOP.value


@dataclass(frozen=True)
class PlaygroundTarget:
    """Resolved playground destination directory and template."""

    target_dir: Path
    template: PlaygroundTemplate
