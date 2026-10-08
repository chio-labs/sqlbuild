"""Identity of the installed and native code behind cached compiler and rule results."""

import hashlib

import sqlbuild._native as _native
from sqlbuild.compiler.frontier._helpers.code_identity import installed_code_identity


def compiled_code_identity() -> str:
    """Return the digest that changes with every released, locally edited, or rebuilt version."""

    return hashlib.sha256(
        f"{installed_code_identity()}\0{_native.BUILD_IDENTITY}".encode()
    ).hexdigest()
