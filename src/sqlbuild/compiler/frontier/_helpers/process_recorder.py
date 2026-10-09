"""The process's debug recorder of native fallbacks and answers, created once."""

from functools import cache

from sqlbuild.compiler.frontier.classes.native_fallback_recorder import NativeFallbackRecorder


@cache
def process_recorder() -> NativeFallbackRecorder | None:
    """Return the recorder when the debug record directory is set, otherwise None."""

    return NativeFallbackRecorder.from_environment()
