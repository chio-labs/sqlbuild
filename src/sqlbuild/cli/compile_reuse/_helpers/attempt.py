"""Decide whether a compile can replay the stored result, and replay it on a hit."""

from __future__ import annotations

import os
import time

from sqlbuild.cli.compile_reuse._helpers.launch_records import write_launch_record
from sqlbuild.cli.compile_reuse._helpers.native_reuse import native_attempt
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt, CompileReuseRequest
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome


def attempt_reuse(*, request: CompileReuseRequest) -> CompileReuseAttempt:
    """Replay a stored compile when every input matches, otherwise prepare to store one."""

    started: float = time.monotonic()
    project_dir: str = os.path.abspath(
        os.getcwd() if request.project_dir is None else request.project_dir
    )
    attempt: CompileReuseAttempt = native_attempt(
        request=request, project_dir=project_dir, started=started
    )
    if attempt.outcome is CompileReuseOutcome.HIT:
        write_launch_record(attempt=attempt)
    return attempt
