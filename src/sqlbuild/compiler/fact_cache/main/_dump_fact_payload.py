"""Public entry for serializing one local cache value with the fact-cache codec."""

from __future__ import annotations

from sqlbuild.compiler.fact_cache._helpers.restricted_pickle import dump_fact_payload


def dumped_fact_payload(value: object) -> bytes:
    """Serialize one cache value with the fixed fact-cache protocol."""

    return dump_fact_payload(value)
