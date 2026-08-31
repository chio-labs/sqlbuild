from dataclasses import dataclass

from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.contracts.models import SnapshotsConfig


@dataclass(frozen=True)
class SnapshotFullRefreshPolicyTestCase:
    description: str
    plan_output: PlanOutput
    snapshots_config: SnapshotsConfig
    allow_snapshot_full_refresh: bool
    expected_error_fragment: str | None = None
    expected_help_fragment: str = ""
    expected_output: str = ""
    input_text: str = ""
    input_is_tty: bool = False


@dataclass(frozen=True)
class TableTypeDowngradePolicyTestCase:
    description: str
    plan_output: PlanOutput
    allow_table_type_downgrade: bool
    expected_error_fragment: str | None = None
    expected_help_fragment: str = ""
    expected_output: str = ""
    input_text: str = ""
    input_is_tty: bool = False
