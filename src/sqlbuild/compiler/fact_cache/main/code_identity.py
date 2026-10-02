"""Public identity of the installed compiler code for derived caches."""

import hashlib

import sqlbuild._native as _native
from sqlbuild.compiler.fact_cache._helpers.code_identity import installed_code_identity


def compiled_code_identity() -> str:
    """Return the digest that changes with every released, locally edited, or rebuilt version."""

    return hashlib.sha256(
        f"{installed_code_identity()}\0{_native.BUILD_IDENTITY}".encode()
    ).hexdigest()
