"""A singular audit header's measurement policy, parsed as attached audit specs are."""

from pathlib import Path

from sqlbuild.compiler.auditing._helpers.schema_audits import (
    parse_measurement_thresholds,
    parse_minimum_samples,
)
from sqlbuild.compiler.auditing.constants import STANDALONE_MEASUREMENT_LABEL
from sqlbuild.compiler.auditing.models import MeasurementThresholds
from sqlbuild.compiler.compile.exceptions import CompileInputError


def parse_audit_header_policies(
    *, header_values: dict[str, object], relative_path: str
) -> tuple[MeasurementThresholds | None, int | None]:
    """The header's `thresholds` and `minimum_samples` specs, raising for invalid ones."""

    file_path: Path = Path(relative_path)
    return (
        parse_measurement_thresholds(
            raw_value=header_values.get("thresholds"),
            file_path=file_path,
            label=STANDALONE_MEASUREMENT_LABEL,
            error_class=CompileInputError,
        ),
        parse_minimum_samples(
            raw_value=header_values.get("minimum_samples"),
            file_path=file_path,
            label=STANDALONE_MEASUREMENT_LABEL,
            error_class=CompileInputError,
        ),
    )
