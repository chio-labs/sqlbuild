"""CLI preview command entrypoint."""

from __future__ import annotations

import argparse

from scripts.cli_preview._helpers.workflow import execute_preview_scene, preview_scenes
from scripts.cli_preview.constants import ALL_SCENES
from scripts.cli_preview.exceptions import PreviewSetupError
from scripts.cli_preview.models import PreviewScene


def run_cli_preview(argv: list[str] | None = None) -> int:
    """Render selected SQLBuild surfaces from temporary real playgrounds."""

    scenes: tuple[PreviewScene, ...] = preview_scenes()
    parser: argparse.ArgumentParser = _build_parser(scenes=scenes)
    arguments: argparse.Namespace = parser.parse_args(argv)
    if arguments.list:
        for scene in scenes:
            print(f"{scene.name:<16} {scene.description}")
        return 0
    selected: tuple[PreviewScene, ...] = _select_scenes(
        scenes=scenes,
        requested_name=arguments.scene,
    )
    try:
        scene: PreviewScene
        for scene in selected:
            return_code: int = execute_preview_scene(
                scene=scene,
                no_color=arguments.no_color,
                keep=arguments.keep,
            )
            if return_code != 0:
                return return_code
    except PreviewSetupError as error:
        parser.error(str(error))
    return 0


def _build_parser(*, scenes: tuple[PreviewScene, ...]) -> argparse.ArgumentParser:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Render real SQLBuild CLI output from temporary DuckDB playgrounds."
    )
    names: tuple[str, ...] = tuple(scene.name for scene in scenes)
    parser.add_argument("scene", nargs="?", choices=(*names, ALL_SCENES), default=ALL_SCENES)
    parser.add_argument("--list", action="store_true", help="list available preview scenes")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI styling")
    parser.add_argument("--keep", action="store_true", help="keep generated playground projects")
    return parser


def _select_scenes(
    *, scenes: tuple[PreviewScene, ...], requested_name: str
) -> tuple[PreviewScene, ...]:
    if requested_name == ALL_SCENES:
        return scenes
    return tuple(scene for scene in scenes if scene.name == requested_name)
