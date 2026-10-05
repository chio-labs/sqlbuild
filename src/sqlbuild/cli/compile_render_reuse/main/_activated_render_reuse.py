"""Public entry for exposing one compile's render reuse to the rendering it runs."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext

from sqlbuild.cli.compile_render_reuse.models import CompileRenderReuse
from sqlbuild.compiler.compile.constants import COMPILE_RENDER_REUSE


def activated_render_reuse(
    *, render_reuse: CompileRenderReuse | None
) -> AbstractContextManager[object]:
    """Activate the render reuse session for the compile block, or do nothing without one."""

    return (
        nullcontext()
        if render_reuse is None
        else COMPILE_RENDER_REUSE.activated(render_reuse.session)
    )
