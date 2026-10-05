"""Public entry for the render layer a finished compile stores with its entry."""

from __future__ import annotations

from sqlbuild.cli.compile_render_reuse._helpers.render_state_file import render_state_layer
from sqlbuild.cli.compile_render_reuse.models import CompileRenderReuse
from sqlbuild.cli.compile_reuse.models import RenderStateLayer
from sqlbuild.compiler.compile.models import RenderReuseState


def stored_render_layer(*, render_reuse: CompileRenderReuse | None) -> RenderStateLayer | None:
    """Return this compile's renders as an overlay on the stored ones, or as a new base."""

    state: RenderReuseState | None = (
        None if render_reuse is None else render_reuse.session.stored_state()
    )
    if render_reuse is None or state is None:
        return None
    layer: RenderStateLayer | None = render_state_layer(state=state, stored=render_reuse.stored)
    if layer is not None:
        return layer
    complete: RenderReuseState | None = render_reuse.session.stored_state(complete=True)
    return None if complete is None else render_state_layer(state=complete, stored=None)
