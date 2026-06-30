"""Public node source watermark payload decoding entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks.main.shared.helpers.payload import (
    decode_watermark_payload as _decode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkPayload


def decode_watermark_payload(value: str, *, qualified_name: str) -> NodeSourceWatermarkPayload:
    """Decode a base64 JSON node source watermark payload."""

    return _decode_watermark_payload(value, qualified_name=qualified_name)
