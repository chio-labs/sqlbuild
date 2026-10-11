"""A compiled seed as a `CompiledSeed` record, for callers that copy or expose it."""

from sqlbuild.compiler.compile.models import CompiledSeed
from sqlbuild.compiler.compile.types import CompiledSeedView
from sqlbuild.compiler.compiled_project._helpers.model_updates import compiled_seed_record_impl


def compiled_seed_record(seed: CompiledSeedView) -> CompiledSeed:
    """The seed as a `CompiledSeed`, projected from its owner when it is a native view."""

    return compiled_seed_record_impl(seed)
