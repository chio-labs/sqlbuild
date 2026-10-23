"""The relation usage report of an adapter that cannot tell who reads its relations."""

from __future__ import annotations

from sqlbuild.adapter.contract.constants import UNSUPPORTED_RELATION_USAGE_REASON
from sqlbuild.adapter.contract.models import RelationUsageReport


def unsupported_relation_usage() -> RelationUsageReport:
    """Report that usage was not checked because the adapter has no usage source."""

    return RelationUsageReport(checked=False, reason=UNSUPPORTED_RELATION_USAGE_REASON)
