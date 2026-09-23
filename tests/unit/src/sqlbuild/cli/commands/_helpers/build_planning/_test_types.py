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


@dataclass(frozen=True)
class ModelExecutionLimitTestCase:
    description: str
    model_count: int
    maximum_models: int
    remediation: str | None = None
    expected_code: str | None = None


@dataclass(frozen=True)
class UnsupportedDurationLimitTestCase:
    description: str
    max_duration: str
    remediation: str
    expected_code: str
    expected_error_fragment: str


@dataclass(frozen=True)
class RetentionDecreasePolicyTestCase:
    description: str
    plan_output: PlanOutput
    allow_retention_decrease: bool
    expected_error_fragment: str | None = None
    expected_help_fragment: str = ""
    expected_output: str = ""
    input_text: str = ""
    input_is_tty: bool = False
