"""Count work a native stage answered itself, so a stage switched to Python is noticed."""

from sqlbuild.compiler.frontier._helpers.process_recorder import process_recorder
from sqlbuild.compiler.frontier.classes.native_fallback_recorder import NativeFallbackRecorder
from sqlbuild.compiler.frontier.constants import NATIVE_ANSWER_SITE_SUFFIX
from sqlbuild.compiler.frontier.types import NativeStage


def report_native_answer(*, stage: NativeStage, kind: str, units: int = 1) -> None:
    """Record `units` of work of the sort `kind` that `stage` answered natively, when recording."""

    recorder: NativeFallbackRecorder | None = process_recorder()
    if recorder is not None and units:
        recorder.record(site=f"{stage.value}{NATIVE_ANSWER_SITE_SUFFIX}", kind=kind, units=units)
