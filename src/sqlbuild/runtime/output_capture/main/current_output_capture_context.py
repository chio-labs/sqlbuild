"""Active output capture context lookup."""

from sqlbuild.runtime.output_capture._helpers.scope import (
    current_output_capture_context as _current_output_capture_context,
)
from sqlbuild.runtime.output_capture.models import OutputCaptureContext


def current_output_capture_context() -> OutputCaptureContext | None:
    """Return optional integration context for the active command."""

    return _current_output_capture_context()
