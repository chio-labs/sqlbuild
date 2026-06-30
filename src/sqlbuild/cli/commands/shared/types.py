"""Shared CLI domain types."""

from __future__ import annotations

from enum import StrEnum


class CliCommand(StrEnum):
    COMPILE = "compile"
    DAG = "dag"
    PLAN = "plan"
    FRESHNESS = "freshness"
    BUILD = "build"
    TEST = "test"
    CHECK = "check"
    AUDIT = "audit"
    LOAD = "load"
    SEED = "seed"
    CLONE = "clone"
    DIFF = "diff"
    RECONCILE = "reconcile"
    PROMOTE = "promote"
    ROLLBACK = "rollback"
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
