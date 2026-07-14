"""Build the dbt fingerprint destination."""

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt._helpers.manifest.fingerprinting import (
    build_dbt_fingerprint_destination as _build,
)
from sqlbuild.integrations.dbt.models import DbtFingerprintDestination


def build_dbt_fingerprint_destination(project: CompiledProject) -> DbtFingerprintDestination:
    """Return the run-scoped dbt fingerprint destination."""

    return _build(project)
