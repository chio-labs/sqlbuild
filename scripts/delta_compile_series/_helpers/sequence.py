"""Apply the named edits of a fixed delta compile sequence."""

from __future__ import annotations

import random
from pathlib import Path

from scripts.delta_compile_series._helpers.edits import applied, project_files
from scripts.delta_compile_series.constants import (
    BODY_EDIT,
    BODY_MODEL_INDEX,
    BODY_SEED,
    DOUBLE_CAST,
    DOUBLE_COLUMN,
    FLOAT_CAST,
    FLOAT_COLUMN,
)
from scripts.delta_compile_series.exceptions import DeltaCompileSeriesError
from scripts.delta_compile_series.types import SequenceEdit


def reshaped(*, project_dir: Path) -> Path:
    """Change the first model whose first quantity is a DOUBLE to output a FLOAT instead."""

    models: list[Path] = project_files(project_dir=project_dir, edit=BODY_EDIT)
    path: Path = next(path for path in models if DOUBLE_COLUMN in path.read_text("utf-8"))
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace(DOUBLE_COLUMN, FLOAT_COLUMN, 1)
        .replace(DOUBLE_CAST, FLOAT_CAST),
        encoding="utf-8",
    )
    return path


def edited_body(*, project_dir: Path) -> Path:
    """Change a constant in one model's query."""

    model: Path = project_files(project_dir=project_dir, edit=BODY_EDIT)[BODY_MODEL_INDEX]
    if not applied(path=model, edit=BODY_EDIT, rng=random.Random(BODY_SEED)):
        raise DeltaCompileSeriesError(f"the body edit does not apply to {model.name}")
    return model


def sequence_edited(*, project_dir: Path, edit: SequenceEdit) -> Path | None:
    """Apply `edit`; return the file it changed, if any."""

    if edit is SequenceEdit.BODY:
        return edited_body(project_dir=project_dir)
    if edit is SequenceEdit.SHAPE:
        return reshaped(project_dir=project_dir)
    return None
