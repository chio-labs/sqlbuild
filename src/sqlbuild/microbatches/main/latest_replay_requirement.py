"""Public active replay-requirement selection entrypoint."""

from sqlbuild.microbatches._helpers.projection import (
    latest_active_replay_requirement as _latest_active_replay_requirement,
)
from sqlbuild.microbatches.models import MicrobatchEvent


def latest_active_replay_requirement(
    *, events: tuple[MicrobatchEvent, ...], current_model_version_hash: str
) -> MicrobatchEvent | None:
    """Return the latest requirement for the currently expected model version."""

    return _latest_active_replay_requirement(
        events=events, current_model_version_hash=current_model_version_hash
    )
