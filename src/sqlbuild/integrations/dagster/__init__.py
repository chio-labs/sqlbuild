"""Optional Dagster integration for SQLBuild."""

from sqlbuild.integrations.dagster.assets import sqlbuild_assets
from sqlbuild.integrations.dagster.helpers.invocation import SqlBuildCliInvocation
from sqlbuild.integrations.dagster.project import SqlBuildProject
from sqlbuild.integrations.dagster.resource import SqlBuildCliResource
from sqlbuild.integrations.dagster.translator import SqlBuildDagsterTranslator

__all__ = [
    "SqlBuildCliInvocation",
    "SqlBuildCliResource",
    "SqlBuildDagsterTranslator",
    "SqlBuildProject",
    "sqlbuild_assets",
]
