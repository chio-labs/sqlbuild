"""Resource name validation exceptions."""

from __future__ import annotations

from sqlbuild.compiler.discovery.exceptions import DiscoveryError


class ResourceIdentityError(DiscoveryError):
    """Raised when an authored resource identity is not canonical snake_case."""

    code: str = "D016"
