"""Deterministic audit result identity helpers."""

from hashlib import sha256


def build_audit_result_id(
    *,
    invocation_id: str,
    run_id: str,
    binding_key: str,
    execution_fingerprint: str,
    run_scope_phase: str,
    attempt_key: str | None = None,
) -> str:
    """Build a deterministic result ID at caller-selected attempt granularity."""

    discriminator: str = "" if attempt_key is None else attempt_key
    identity: str = ":".join(
        (
            invocation_id,
            run_id,
            binding_key,
            execution_fingerprint,
            run_scope_phase,
            discriminator,
        )
    )
    return sha256(identity.encode("utf-8")).hexdigest()
