"""Structured values shared by CLI output renderers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlbuild.cli.output._helpers.integration_identity import integration_resource_id
from sqlbuild.cli.output._helpers.integration_validation import (
    encode_integration_json,
    validate_allowlisted_mapping,
    validate_identifier,
    validate_maximum_start_safety,
    validate_optional_identifier,
)
from sqlbuild.cli.output.constants import (
    INTEGRATION_ASSET_KINDS,
    INTEGRATION_ASSET_STATUSES,
    INTEGRATION_CHECK_ATTACHMENT_KINDS,
    INTEGRATION_CHECK_KINDS,
    INTEGRATION_CHECK_PASS_STATUS,
    INTEGRATION_CHECK_RUN_SCOPE_PHASES,
    INTEGRATION_CHECK_SEVERITIES,
    INTEGRATION_CHECK_STATUSES,
    INTEGRATION_CLONE_ACTIONS,
    INTEGRATION_FAILED_PHASES,
    INTEGRATION_FAILED_STATUS,
    INTEGRATION_FUTURE_CURSOR_KEYS,
    INTEGRATION_MICROBATCH_COUNT_KEYS,
    INTEGRATION_MICROBATCH_KEYS,
    INTEGRATION_MICROBATCH_LIMIT_ACTIONS,
    INTEGRATION_MICROBATCH_PARTITION_POLICIES,
    INTEGRATION_MICROBATCH_REPLAY_STATES,
    INTEGRATION_MICROBATCH_RUN_TYPES,
    INTEGRATION_RESOURCE_FAILED_EVENT,
    INTEGRATION_RESOURCE_KINDS,
    INTEGRATION_RESULT_RECORD_KIND,
    INTEGRATION_RESULT_SCHEMA_VERSION,
    INTEGRATION_SKIP_MODES,
    INTEGRATION_SKIPPED_STATUS,
    MAX_INTEGRATION_COLLECTION_ITEMS,
    MAX_INTEGRATION_RECORD_BYTES,
)
from sqlbuild.cli.output.types import (
    CursorBoundsOwner,
    CursorResolutionStatus,
    IntegrationOutputKind,
)
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.runtime.observability.constants import (
    RESOURCE_ATTEMPT_SKIPPED_EVENT,
    RESOURCE_SKIP_CODES,
    RESOURCE_TERMINALS,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue


@dataclass(frozen=True)
class CursorPlanDetails:
    """Operator-facing cursor details shared by plan renderers."""

    requested_start: str | None
    requested_end: str | None
    bounds_owner: CursorBoundsOwner
    resolution_status: CursorResolutionStatus
    resolved_bounds: CursorBounds | None
    declared_grain: str | None
    effective_grain: str | None
    declared_batch_size: str | None
    effective_batch_size: str | None
    planned_batch_count: int | None


@dataclass(frozen=True)
class TerminalEventClaim:
    """One claimed terminal with its immutable canonical publication sequence."""

    terminal: LifecycleEvent
    event_sequence: int


@dataclass(frozen=True)
class IntegrationAssetResult:
    """Bounded asset enrichment consumed by SQLBuild-owned integrations."""

    kind: str
    name: str
    status: str
    action: str | None = None
    target: str | None = None
    origin_relation: str | None = None
    staging_relation: str | None = None
    failed_phase: str | None = None
    loader: str | None = None
    rows_loaded: int | None = None
    materialized: bool | None = None
    future_cursor_safety: Mapping[str, JSONValue] = field(default_factory=dict)
    maximum_start_safety: Mapping[str, JSONValue] = field(default_factory=dict)
    microbatch: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(value=self.kind, field_name="asset kind")
        validate_identifier(value=self.name, field_name="asset name")
        if self.kind not in INTEGRATION_ASSET_KINDS:
            raise ObservabilityValidationError("integration asset kind is unsupported")
        if self.status not in INTEGRATION_ASSET_STATUSES:
            raise ObservabilityValidationError("integration asset status is unsupported")
        if self.action is not None and self.action not in INTEGRATION_CLONE_ACTIONS:
            raise ObservabilityValidationError("integration asset action is unsupported")
        if self.failed_phase is not None and self.failed_phase not in INTEGRATION_FAILED_PHASES:
            raise ObservabilityValidationError("integration asset failed_phase is unsupported")
        for field_name, value in (
            ("target", self.target),
            ("origin_relation", self.origin_relation),
            ("staging_relation", self.staging_relation),
            ("failed_phase", self.failed_phase),
            ("loader", self.loader),
        ):
            validate_optional_identifier(value=value, field_name=field_name)
        if self.rows_loaded is not None and (
            type(self.rows_loaded) is not int or self.rows_loaded < 0
        ):
            raise ObservabilityValidationError("integration rows_loaded must be non-negative")
        if self.materialized is not None and type(self.materialized) is not bool:
            raise ObservabilityValidationError("integration materialized must be boolean")
        validate_allowlisted_mapping(
            value=self.future_cursor_safety,
            field_name="future_cursor_safety",
            allowed_keys=INTEGRATION_FUTURE_CURSOR_KEYS,
        )
        validate_allowlisted_mapping(
            value=self.microbatch,
            field_name="microbatch",
            allowed_keys=INTEGRATION_MICROBATCH_KEYS,
        )
        validate_maximum_start_safety(self.maximum_start_safety)
        for key in INTEGRATION_MICROBATCH_COUNT_KEYS:
            count: object = self.microbatch.get(key)
            if count is not None and (type(count) is not int or count < 0):
                raise ObservabilityValidationError(
                    f"integration microbatch {key} must be non-negative integer"
                )
        for value, field_name, allowed in (
            (self.microbatch.get("run_type"), "run_type", INTEGRATION_MICROBATCH_RUN_TYPES),
            (self.microbatch.get("action"), "action", INTEGRATION_MICROBATCH_LIMIT_ACTIONS),
            (
                self.microbatch.get("unaccounted_partition_policy"),
                "unaccounted_partition_policy",
                INTEGRATION_MICROBATCH_PARTITION_POLICIES,
            ),
            (
                self.microbatch.get("replay_requirement_state"),
                "replay_requirement_state",
                INTEGRATION_MICROBATCH_REPLAY_STATES,
            ),
        ):
            if value is not None and (type(value) is not str or value not in allowed):
                raise ObservabilityValidationError(
                    f"integration microbatch {field_name} is unsupported"
                )
        concurrent_enabled: object = self.microbatch.get("concurrent_enabled")
        if concurrent_enabled is not None and type(concurrent_enabled) is not bool:
            raise ObservabilityValidationError(
                "integration microbatch concurrent_enabled must be boolean"
            )


@dataclass(frozen=True)
class IntegrationCheckResult:
    """Bounded check enrichment consumed by SQLBuild-owned integrations."""

    kind: str
    name: str
    check_id: str
    passed: bool
    status: str
    dag_check_id: str | None = None
    severity: str | None = None
    asset_name: str | None = None
    attachment_kind: str | None = None
    attached_column_name: str | None = None
    attached_target_name: str | None = None
    run_scope_phase: str | None = None
    row_count: int | None = None
    reused: bool | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("check kind", self.kind),
            ("check name", self.name),
            ("check id", self.check_id),
        ):
            validate_identifier(value=value, field_name=field_name)
        validate_optional_identifier(value=self.dag_check_id, field_name="dag_check_id")
        if self.kind not in INTEGRATION_CHECK_KINDS:
            raise ObservabilityValidationError("integration check kind is unsupported")
        if self.status not in INTEGRATION_CHECK_STATUSES:
            raise ObservabilityValidationError("integration check status is unsupported")
        if type(self.passed) is not bool:
            raise ObservabilityValidationError("integration check passed must be boolean")
        if self.passed != (self.status == INTEGRATION_CHECK_PASS_STATUS):
            raise ObservabilityValidationError("integration check status and passed are incoherent")
        if self.severity is not None and self.severity not in INTEGRATION_CHECK_SEVERITIES:
            raise ObservabilityValidationError("integration check severity is unsupported")
        if (
            self.attachment_kind is not None
            and self.attachment_kind not in INTEGRATION_CHECK_ATTACHMENT_KINDS
        ):
            raise ObservabilityValidationError("integration check attachment_kind is unsupported")
        if (
            self.run_scope_phase is not None
            and self.run_scope_phase not in INTEGRATION_CHECK_RUN_SCOPE_PHASES
        ):
            raise ObservabilityValidationError("integration check run_scope_phase is unsupported")
        for field_name, value in (
            ("asset_name", self.asset_name),
            ("attachment_kind", self.attachment_kind),
            ("attached_column_name", self.attached_column_name),
            ("attached_target_name", self.attached_target_name),
            ("run_scope_phase", self.run_scope_phase),
        ):
            validate_optional_identifier(value=value, field_name=field_name)
        if self.row_count is not None and (type(self.row_count) is not int or self.row_count < 0):
            raise ObservabilityValidationError("integration check row_count must be non-negative")
        if self.reused is not None and type(self.reused) is not bool:
            raise ObservabilityValidationError("integration check reused must be boolean")


@dataclass(frozen=True)
class IntegrationResultEnvelope:
    """Versioned canonical terminal and typed integration result envelope."""

    schema_version: int
    record_kind: str
    event_id: str
    event_sequence: int
    event_type: str
    occurred_at: str
    invocation_id: str
    run_id: str
    resource_id: str
    resource_attempt_id: str
    operation_id: str | None
    statement_id: str | None
    resource_kind: str
    resource_name: str
    attempt_number: int
    duration_ms: int | float | None
    output_kind: IntegrationOutputKind
    command: str
    error_code: str | None = None
    error_type: str | None = None
    skip_code: str | None = None
    skip_mode: str | None = None
    projection_degraded: bool = False
    asset: IntegrationAssetResult | None = None
    checks: tuple[IntegrationCheckResult, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != INTEGRATION_RESULT_SCHEMA_VERSION
        ):
            raise ObservabilityValidationError(
                f"unsupported integration result schema_version: {self.schema_version}"
            )
        if self.record_kind != INTEGRATION_RESULT_RECORD_KIND:
            raise ObservabilityValidationError(
                f"unsupported integration result record_kind: {self.record_kind}"
            )
        if self.event_type not in RESOURCE_TERMINALS:
            raise ObservabilityValidationError(
                f"integration result event_type is not a resource terminal: {self.event_type}"
            )
        required_text: tuple[str, ...] = (
            self.event_id,
            self.event_type,
            self.occurred_at,
            self.invocation_id,
            self.run_id,
            self.resource_id,
            self.resource_attempt_id,
            self.resource_kind,
            self.resource_name,
            self.command,
        )
        if any(not isinstance(value, str) or not value for value in required_text):
            raise ObservabilityValidationError(
                "integration result identity fields must be non-empty"
            )
        for field_name, value in (
            ("event_id", self.event_id),
            ("invocation_id", self.invocation_id),
            ("run_id", self.run_id),
            ("resource_id", self.resource_id),
            ("resource_attempt_id", self.resource_attempt_id),
            ("resource_kind", self.resource_kind),
            ("resource_name", self.resource_name),
            ("command", self.command),
        ):
            validate_identifier(value=value, field_name=field_name)
        if self.resource_kind not in INTEGRATION_RESOURCE_KINDS:
            raise ObservabilityValidationError("integration resource_kind is unsupported")
        validate_optional_identifier(value=self.operation_id, field_name="operation_id")
        validate_optional_identifier(value=self.statement_id, field_name="statement_id")
        try:
            occurred_at: datetime = datetime.fromisoformat(self.occurred_at)
        except ValueError as error:
            raise ObservabilityValidationError(
                "integration result occurred_at must be an ISO-8601 timestamp"
            ) from error
        if occurred_at.utcoffset() is None:
            raise ObservabilityValidationError(
                "integration result occurred_at must include a timezone"
            )
        if type(self.event_sequence) is not int or self.event_sequence < 0:
            raise ObservabilityValidationError(
                "integration result event_sequence must be non-negative"
            )
        if (
            not isinstance(self.attempt_number, int)
            or isinstance(self.attempt_number, bool)
            or self.attempt_number < 1
        ):
            raise ObservabilityValidationError("integration result attempt_number must be positive")
        if self.asset is None and not self.checks:
            raise ObservabilityValidationError(
                "integration result must contain asset or check enrichment"
            )
        if self.duration_ms is not None and (
            type(self.duration_ms) not in (int, float)
            or not math.isfinite(self.duration_ms)
            or self.duration_ms < 0
        ):
            raise ObservabilityValidationError(
                "integration result duration_ms must be non-negative"
            )
        for field_name, value in (
            ("error_code", self.error_code),
            ("error_type", self.error_type),
            ("skip_code", self.skip_code),
            ("skip_mode", self.skip_mode),
        ):
            validate_optional_identifier(value=value, field_name=field_name)
        if type(self.projection_degraded) is not bool:
            raise ObservabilityValidationError(
                "integration result projection_degraded must be boolean"
            )
        self._validate_result_identity()
        self._validate_terminal_facts()

    def to_json(self) -> str:
        """Encode one validated envelope as a JSON Lines record."""

        payload: dict[str, Any] = asdict(self)
        payload["output_kind"] = self.output_kind.value
        return encode_integration_json(value=payload, record=True) + "\n"

    def _validate_result_identity(self) -> None:
        if self.output_kind == IntegrationOutputKind.ASSET:
            if self.asset is None or self.checks:
                raise ObservabilityValidationError("asset output must contain exactly one asset")
            if self.asset.kind != self.resource_kind or self.asset.name != self.resource_name:
                raise ObservabilityValidationError(
                    "integration asset identity does not match terminal"
                )
            expected_id: str = integration_resource_id(
                resource_kind=self.resource_kind,
                resource_name=self.resource_name,
                check_id=None,
                loader_name=self.asset.loader,
            )
            if self.resource_id != expected_id:
                raise ObservabilityValidationError("integration asset resource_id is incoherent")
            return
        if self.output_kind == IntegrationOutputKind.CHECK:
            if self.asset is not None or len(self.checks) != 1:
                raise ObservabilityValidationError("check output must contain exactly one check")
            if self.checks[0].check_id != self.resource_id:
                raise ObservabilityValidationError(
                    "integration check identity does not match terminal"
                )
            return
        raise ObservabilityValidationError("integration result output_kind is unsupported")

    def _validate_terminal_facts(self) -> None:
        if self.event_type == INTEGRATION_RESOURCE_FAILED_EVENT:
            if self.error_type is None or self.skip_code is not None or self.skip_mode is not None:
                raise ObservabilityValidationError("failed integration terminal facts are invalid")
            if self.asset is not None and self.asset.status != INTEGRATION_FAILED_STATUS:
                raise ObservabilityValidationError("failed terminal asset status is incoherent")
            return
        if self.event_type == RESOURCE_ATTEMPT_SKIPPED_EVENT:
            if (
                self.skip_code not in RESOURCE_SKIP_CODES
                or self.error_code is not None
                or self.error_type is not None
                or (self.skip_mode is not None and self.skip_mode not in INTEGRATION_SKIP_MODES)
            ):
                raise ObservabilityValidationError("skipped integration terminal facts are invalid")
            if self.asset is not None and self.asset.status != INTEGRATION_SKIPPED_STATUS:
                raise ObservabilityValidationError("skipped terminal asset status is incoherent")
            return
        if any(
            value is not None
            for value in (self.error_code, self.error_type, self.skip_code, self.skip_mode)
        ):
            raise ObservabilityValidationError("completed integration terminal has failure facts")

    @classmethod
    def from_json(cls, value: str) -> IntegrationResultEnvelope:
        """Decode and validate one integration result JSON record."""

        if len(value.encode("utf-8")) > MAX_INTEGRATION_RECORD_BYTES:
            raise ObservabilityValidationError("integration result record exceeds size limit")
        try:
            payload: Any = json.loads(value)
        except json.JSONDecodeError as error:
            raise ObservabilityValidationError("malformed integration result JSON") from error
        if not isinstance(payload, dict):
            raise ObservabilityValidationError("integration result must be a JSON object")
        if (
            type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != INTEGRATION_RESULT_SCHEMA_VERSION
        ):
            raise ObservabilityValidationError(
                f"unsupported integration result schema_version: {payload.get('schema_version')}"
            )
        if payload.get("record_kind") != INTEGRATION_RESULT_RECORD_KIND:
            raise ObservabilityValidationError(
                f"unsupported integration result record_kind: {payload.get('record_kind')}"
            )
        asset_payload: object = payload.pop("asset", None)
        checks_payload: object = payload.pop("checks", ())
        if asset_payload is not None and not isinstance(asset_payload, dict):
            raise ObservabilityValidationError("integration result asset must be an object")
        if not isinstance(checks_payload, list | tuple):
            raise ObservabilityValidationError("integration result checks must be an array")
        if len(checks_payload) > MAX_INTEGRATION_COLLECTION_ITEMS:
            raise ObservabilityValidationError("integration result checks exceed item limit")
        try:
            output_kind: IntegrationOutputKind = IntegrationOutputKind(payload.pop("output_kind"))
            asset: IntegrationAssetResult | None = (
                IntegrationAssetResult(**asset_payload) if isinstance(asset_payload, dict) else None
            )
            checks: tuple[IntegrationCheckResult, ...] = tuple(
                IntegrationCheckResult(**check_payload)
                for check_payload in checks_payload
                if isinstance(check_payload, dict)
            )
            if len(checks) != len(checks_payload):
                raise ObservabilityValidationError(
                    "integration result checks must contain only objects"
                )
            return cls(
                **payload,
                output_kind=output_kind,
                asset=asset,
                checks=checks,
            )
        except ObservabilityValidationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ObservabilityValidationError("invalid integration result envelope") from error
