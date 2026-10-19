"""Enumerations of delta compile series."""

from __future__ import annotations

from enum import StrEnum


class EditTarget(StrEnum):
    """Which project files an edit changes."""

    MODELS = "models"
    TESTS = "tests"
    PROJECT_CONFIG = "project_config"


class SequenceEdit(StrEnum):
    """One step of a fixed edit sequence."""

    BODY = "body"
    SHAPE = "shape"
    NONE = "none"
