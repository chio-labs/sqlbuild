"""Authoring helpers for SQLBuild-managed warehouse functions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def udf(**kwargs: object) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a Python function as a SQLBuild UDF for static project discovery."""

    del kwargs

    def _decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        return function

    return _decorate
