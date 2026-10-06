"""Dump frontier objects as canonical JSON so two engines can be compared stage by stage."""

import json
import os
from pathlib import Path

from sqlbuild.compiler.frontier.classes.stage_capture_encoder import StageCaptureEncoder
from sqlbuild.compiler.frontier.classes.stage_capture_sequence import StageCaptureSequence
from sqlbuild.compiler.frontier.constants import STAGE_CAPTURE_DIR_ENV_VAR, STAGE_CAPTURE_SUFFIX
from sqlbuild.compiler.frontier.types import CompilerStage


def write_stage_capture(*, stage: CompilerStage, value: object) -> None:
    """Write one frontier object when SQLBUILD_COMPILER_STAGE_CAPTURE_DIR names a directory."""

    directory: str | None = os.environ.get(STAGE_CAPTURE_DIR_ENV_VAR)
    if not directory:
        return
    path: Path = Path(directory) / (
        f"{StageCaptureSequence.next_value():03d}-{stage.value}{STAGE_CAPTURE_SUFFIX}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(render_stage_capture(value), encoding="utf-8")


def render_stage_capture(value: object) -> str:
    """Render a value as indented JSON that keeps insertion order and sorts only sets."""

    return (
        json.dumps(
            StageCaptureEncoder().encode(value),
            indent=1,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
