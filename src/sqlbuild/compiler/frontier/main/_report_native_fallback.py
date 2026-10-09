"""Count one place where a shipped native stage handed its work back to Python."""

from functools import cache

from sqlbuild.compiler.frontier.classes.native_fallback_recorder import NativeFallbackRecorder
from sqlbuild.compiler.frontier.constants import NATIVE_FALLBACK_DEFAULT_KIND
from sqlbuild.compiler.frontier.types import NativeFallbackSite


def report_native_fallback(
    *, site: NativeFallbackSite, kind: str = NATIVE_FALLBACK_DEFAULT_KIND
) -> None:
    """Record a fallback at `site` when the debug record directory is set; otherwise do nothing."""

    recorder: NativeFallbackRecorder | None = _process_recorder()
    if recorder is not None:
        recorder.record(site=site.value, kind=kind)


@cache
def _process_recorder() -> NativeFallbackRecorder | None:
    return NativeFallbackRecorder.from_environment()
