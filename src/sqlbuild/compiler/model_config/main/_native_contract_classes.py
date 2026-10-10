"""Contract classes native header parsing builds Python columns and audits from."""

from functools import cache

from sqlbuild.compiler.auditing.models import MeasurementThresholdBound, MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditSeverity, ThresholdOperator
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn


@cache
def native_contract_classes() -> dict[str, object]:
    """The contract classes native header parsing builds columns and audits as."""

    return {
        "schema_column": SchemaColumn,
        "schema_audit_instance": SchemaAuditInstance,
        "measurement_thresholds": MeasurementThresholds,
        "measurement_threshold_bound": MeasurementThresholdBound,
        "severities": {severity.value: severity for severity in AuditSeverity},
        "threshold_operators": {operator.value: operator for operator in ThresholdOperator},
        "allocate": object.__new__,
    }
