"""Public entry for replaying the previous compile when no compile input changed."""

from __future__ import annotations

from sqlbuild.cli.compile_reuse._helpers.attempt import attempt_reuse
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt, CompileReuseRequest


def attempt_compile_reuse(*, request: CompileReuseRequest) -> CompileReuseAttempt:
    """Replay the stored compile on a hit, otherwise return the state a full compile stores."""

    return attempt_reuse(request=request)
