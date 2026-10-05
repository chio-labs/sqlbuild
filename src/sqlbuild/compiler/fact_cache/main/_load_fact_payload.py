"""Public entry for reading one local cache value through the restricted fact-cache codec."""

from __future__ import annotations

from sqlbuild.compiler.fact_cache._helpers.restricted_pickle import load_fact_payload


def loaded_fact_payload(payload: bytes | memoryview) -> object:
    """Deserialize one verified cache payload through the restricted class allowlist."""

    return load_fact_payload(payload)
