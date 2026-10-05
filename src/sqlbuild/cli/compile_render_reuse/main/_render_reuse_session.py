"""Public entry for the render reuse one full compile runs with."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.compile_render_reuse._helpers.load_notice import (
    finish_load_notice,
    start_load_notice,
)
from sqlbuild.cli.compile_render_reuse._helpers.render_state_file import read_render_state
from sqlbuild.cli.compile_render_reuse.models import CompileRenderReuse, StoredRenderState
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession


def render_reuse_session(*, attempt: CompileReuseAttempt) -> CompileRenderReuse | None:
    """Record renders once a compile is stored, reusing those the changed paths cannot affect."""

    if (
        attempt.outcome is not CompileReuseOutcome.MISS
        or attempt.entry_path is None
        or not attempt.prior_entry
    ):
        return None
    stored: StoredRenderState | None = (
        None
        if attempt.changed_paths is None or attempt.render_state_path is None
        else _loaded_render_state(
            entry_path=attempt.entry_path,
            path=attempt.render_state_path,
            changed_paths=attempt.changed_paths,
        )
    )
    return CompileRenderReuse(
        session=CompileRenderReuseSession(
            prior=None if stored is None else stored.state,
            changed_paths=attempt.changed_paths,
            retained_models=frozenset() if stored is None else stored.layers.overlay_models,
            retained_groups=frozenset() if stored is None else stored.layers.overlay_groups,
        ),
        stored=None if stored is None else stored.layers,
    )


def _loaded_render_state(
    *, entry_path: Path, path: Path, changed_paths: frozenset[str]
) -> StoredRenderState | None:
    started: float | None = start_load_notice(entry_path=entry_path)
    stored: StoredRenderState | None = read_render_state(path=path, changed_paths=changed_paths)
    _ = finish_load_notice(started=started, loaded=stored is not None)
    return stored
