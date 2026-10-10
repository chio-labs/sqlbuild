"""Require a Python whose string semantics the native extension reproduces."""

from __future__ import annotations

from typing import cast

from sqlbuild.compiler.discovery._helpers.native.payloads import native_text_runtime


def require_supported_python() -> tuple[int, int]:
    """The running Python's version; raises `UnsupportedPythonError` where native lacks its text."""

    runtime: dict[str, object] = native_text_runtime()
    return cast(tuple[int, int], runtime["python_version"])
