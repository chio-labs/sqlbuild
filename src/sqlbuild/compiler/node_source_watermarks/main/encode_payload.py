"""Public node source watermark payload encoding entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks.main.shared.helpers.payload import (
    encode_watermark_payload as _encode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkPayload


def encode_watermark_payload(payload: NodeSourceWatermarkPayload) -> str:
    """Encode a node source watermark payload as base64 JSON."""

    return _encode_watermark_payload(payload)
