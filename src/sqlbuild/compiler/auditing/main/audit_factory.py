"""Declare audit-case factories."""

from collections.abc import Callable

from sqlbuild.python_nodes.main.apply_audit_factory import apply_audit_factory


def audit_factory(
    function: Callable[..., object] | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a deterministic, side-effect-free function as an audit-case factory."""

    if function is None:
        return apply_audit_factory
    return apply_audit_factory(function)
