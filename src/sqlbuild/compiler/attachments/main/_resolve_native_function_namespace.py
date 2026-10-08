"""Resolve a function's namespace natively for the preview compiler engine."""

from __future__ import annotations

from dataclasses import asdict

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.models import (
    NativeFunctionNamespace,
    NativeFunctionNamespaceInputs,
)


def resolve_native_function_namespace(
    inputs: NativeFunctionNamespaceInputs,
) -> NativeFunctionNamespace:
    """Return the physical, logical and fingerprint namespace Python's attachment assigns."""

    return NativeFunctionNamespace(*_native.resolve_function_namespace_values(asdict(inputs)))
