"""Scope command-output integration context."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from sqlbuild.runtime.output_capture._helpers.scope import output_capture_context


@contextmanager
def command_output_context(*, external_context: Mapping[str, object]) -> Iterator[None]:
    """Attach opaque integration context to command-output records."""

    with output_capture_context(external_context=external_context):
        yield
