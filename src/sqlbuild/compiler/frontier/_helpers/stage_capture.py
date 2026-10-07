"""Dump frontier objects as canonical JSON so two engines can be compared stage by stage."""

import io
import os
from pathlib import Path
from typing import TextIO

from sqlbuild.compiler.frontier.classes.stage_capture_encoder import StageCaptureEncoder
from sqlbuild.compiler.frontier.classes.stage_capture_sequence import StageCaptureSequence
from sqlbuild.compiler.frontier.classes.stage_capture_writer import StageCaptureWriter
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
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        _write_capture(value=value, stream=stream)


def render_stage_capture(value: object) -> str:
    """Render a value as the JSON document `write_stage_capture` writes."""

    stream: io.StringIO = io.StringIO()
    _write_capture(value=value, stream=stream)
    return stream.getvalue()


def _write_capture(*, value: object, stream: TextIO) -> None:
    writer: StageCaptureWriter = StageCaptureWriter(stream)
    writer.finish(StageCaptureEncoder(on_shared=writer.write_shared).encode(value))
