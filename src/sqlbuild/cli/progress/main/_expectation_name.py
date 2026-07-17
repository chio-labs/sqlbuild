"""Neutral SQL expectation name formatting."""

from __future__ import annotations


def format_expectation_name(model_name: str) -> str:
    """Format a comparison result name as a user-facing expectation name."""

    if model_name.startswith("assertion "):
        return model_name
    return f"expected {model_name}"
