"""Public entry for the render reuse one full compile runs with."""

from __future__ import annotations

from sqlbuild.cli.compile_render_reuse._helpers.render_state_file import read_render_state
from sqlbuild.cli.compile_render_reuse.models import CompileRenderReuse, StoredRenderState
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession


def render_reuse_session(*, attempt: CompileReuseAttempt) -> CompileRenderReuse | None:
    """Start recording renders, reusing the stored ones the changed paths cannot affect."""

    if attempt.outcome is not CompileReuseOutcome.MISS or attempt.entry_path is None:
        return None
    stored: StoredRenderState | None = (
        None
        if attempt.changed_paths is None or attempt.render_state_path is None
        else read_render_state(path=attempt.render_state_path, changed_paths=attempt.changed_paths)
    )
    return CompileRenderReuse(
        session=CompileRenderReuseSession(
            prior=None if stored is None else stored.state, changed_paths=attempt.changed_paths
        ),
        stored=stored,
    )
