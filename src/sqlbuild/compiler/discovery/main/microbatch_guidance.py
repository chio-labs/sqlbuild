"""Entry for the note and help shown when concurrent microbatches are not allowed."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.settings.guidance import (
    microbatch_concurrency_help,
    microbatch_concurrency_note,
)


def microbatch_guidance() -> tuple[str, str]:
    """Return `(note, help)` for `batch_concurrency` above one without the project capability."""

    return microbatch_concurrency_note(), microbatch_concurrency_help()
