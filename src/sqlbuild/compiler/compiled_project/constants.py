"""Constants of the native compiled project and its model loop."""

from sqlbuild.compiler.planner.types import MaterializationType

TABLE_BACKED_MATERIALIZATIONS: tuple[MaterializationType, ...] = (
    MaterializationType.TABLE,
    MaterializationType.INCREMENTAL,
    MaterializationType.SNAPSHOT,
)
