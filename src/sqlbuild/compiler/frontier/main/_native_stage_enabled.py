"""Whether the active compiler engine runs one native stage."""

from sqlbuild.compiler.frontier._helpers.engine import active_compiler_engine
from sqlbuild.compiler.frontier.constants import ENGINE_NATIVE_STAGE_TIERS, NATIVE_STAGE_TIERS
from sqlbuild.compiler.frontier.types import NativeStage


def native_stage_enabled(stage: NativeStage) -> bool:
    """Return whether the active engine includes the tier `stage` is registered at."""

    return NATIVE_STAGE_TIERS[stage] in ENGINE_NATIVE_STAGE_TIERS[active_compiler_engine()]
