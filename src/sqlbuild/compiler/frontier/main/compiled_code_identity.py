"""Identity of the installed and native code behind cached compiler and rule results."""

import sqlbuild._native as _native
from sqlbuild.compiler.frontier._helpers.code_identity import installed_code_identity


def compiled_code_identity() -> str:
    """Return the digest that changes with every released, locally edited, or rebuilt version."""

    return _native.compiled_code_identity(installed_code_identity(), _native.BUILD_IDENTITY)
