"""Shared CLI domain types."""

from __future__ import annotations

from enum import StrEnum


class CliCommand(StrEnum):
    COMPILE = "compile"
    DAG = "dag"
    PLAN = "plan"
    RUN = "run"
    BUILD = "build"
    TEST = "test"
    AUDIT = "audit"
    LOAD = "load"
    SEED = "seed"
    CLONE = "clone"
    DIFF = "diff"
    PROMOTE = "promote"
    DEBUG = "debug"
    LINEAGE = "lineage"
    QUERY = "query"
    CLEAN = "clean"
    JANITOR = "janitor"
    STATE = "state"
    INIT = "init"
    PLAYGROUND = "playground"
    SCENARIO = "scenario"
    DBT = "dbt"
    SKILLS = "skills"
