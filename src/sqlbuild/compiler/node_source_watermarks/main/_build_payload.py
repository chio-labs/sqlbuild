"""Public node source watermark payload computation entrypoint."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.compiler.node_source_watermarks._helpers.context import (
    build_node_source_watermark_payload as _build_node_source_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkPayload
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)


def build_node_source_watermark_payload(
    *,
    required_source_identities: Iterable[SourceFreshnessIdentity],
    direct_source_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord],
    inherited_payloads: Iterable[NodeSourceWatermarkPayload],
) -> NodeSourceWatermarkPayload:
    """Build a node payload from direct and inherited source watermark facts."""

    return _build_node_source_watermark_payload(
        required_source_identities=required_source_identities,
        direct_source_records=direct_source_records,
        inherited_payloads=inherited_payloads,
    )
