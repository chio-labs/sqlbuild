"""Minimal projects whose audits, functions or sources fail while attaching compile inputs."""

from scripts.compiler_differential._helpers.corpus.case_builder import config_files, failure_case
from scripts.compiler_differential.constants import (
    FAILURE_BASE_SOURCES,
    FAILURE_BASE_STAGING,
    FAILURE_SOURCES_PATH,
    FAILURE_STAGING_PATH,
)
from scripts.compiler_differential.models import FailureCase

_STAGING_HEADER: str = '"Staged orders",'
_FLOOR_AUDIT_PATH: str = "models/staging/_sqlbuild/_audits/generic/floor.sql"
_FLOOR_AUDIT: str = 'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE amount < @minimum\n'
_FRESH_AUDIT: str = (
    'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE ordered_at >= __cursor_start()\n'
)
_ORDER_LABEL_PATH: str = "functions/sql/order_label.sql"


def _staging_audits(audits: str) -> dict[str, str]:
    return {
        FAILURE_STAGING_PATH: FAILURE_BASE_STAGING.replace(
            _STAGING_HEADER, f"{_STAGING_HEADER}\n  audits [{audits}],"
        )
    }


def _order_label(header: str) -> dict[str, str]:
    return {_ORDER_LABEL_PATH: f"FUNCTION (\n{header});\n\nUPPER(p_status)\n"}


def attachment_failure_cases() -> tuple[FailureCase, ...]:
    """Return audit, function and source attachment failures the native stage reports."""

    return (
        failure_case(
            name="generic-audit-unknown-run-scope",
            expected_code="P001",
            expected_message="unknown audit run_scope 'always'",
            files={
                _FLOOR_AUDIT_PATH: _FLOOR_AUDIT,
                **_staging_audits('floor (minimum 0, run_scope "always")'),
            },
        ),
        failure_case(
            name="generic-audit-overrides-implicit-model",
            expected_code="P001",
            expected_message="must not override implicit model from attached context",
            files={
                _FLOOR_AUDIT_PATH: _FLOOR_AUDIT,
                **_staging_audits('floor (minimum 0, model "customer_totals")'),
            },
        ),
        failure_case(
            name="generic-audit-cursor-intrinsic",
            expected_code="P001",
            expected_message="Audit 'fresh' uses cursor intrinsics",
            files={
                "models/staging/_sqlbuild/_audits/generic/fresh.sql": _FRESH_AUDIT,
                **_staging_audits("fresh"),
            },
        ),
        failure_case(
            name="audit-unknown-project-variable",
            expected_code="P001",
            expected_message="unknown project variable '@@floor_amount'",
            files={
                **config_files('\n[vars]\nregion = "north"\n'),
                _FLOOR_AUDIT_PATH: _FLOOR_AUDIT.replace("@minimum", "@@floor_amount"),
                **_staging_audits("floor"),
            },
        ),
        failure_case(
            name="audit-variable-in-doubled-backticks",
            expected_code="P001",
            expected_message="unknown project variable '@@floor_amount'",
            files={
                **config_files('\n[vars]\nregion = "north"\n'),
                _FLOOR_AUDIT_PATH: _FLOOR_AUDIT.replace("@minimum", "`@@floor_amount``"),
                **_staging_audits("floor"),
            },
        ),
        failure_case(
            name="sql-function-missing-returns",
            expected_code="P001",
            expected_message="functions/sql/order_label.sql must declare returns",
            files=_order_label('  description "Order label",\n  arguments (p_status VARCHAR),\n'),
        ),
        failure_case(
            name="sql-function-template-namespace",
            expected_code="P001",
            expected_message="references unsupported template namespace 'VAR'",
            files=_order_label(
                '  description "Order label",\n  arguments (p_status VARCHAR),\n'
                '  returns "${VAR:label_type}",\n'
            ),
        ),
        failure_case(
            name="source-description-unknown-variable",
            expected_code="P001",
            expected_message="references unknown variable 'channel'",
            files={
                FAILURE_SOURCES_PATH: FAILURE_BASE_SOURCES.replace(
                    "description: Orders feed.", 'description: "Orders from ${channel}"'
                )
            },
        ),
    )
