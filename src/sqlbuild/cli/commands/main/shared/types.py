"""Shared CLI domain types."""

from __future__ import annotations

from enum import StrEnum


class CliCommand(StrEnum):
    COMPILE = "compile"
    PLAN = "plan"
    RUN = "run"
    BUILD = "build"
    TEST = "test"
    AUDIT = "audit"
    SEED = "seed"
    CLONE = "clone"
    DIFF = "diff"
    CLEAN = "clean"
    JANITOR = "janitor"
    INIT = "init"
