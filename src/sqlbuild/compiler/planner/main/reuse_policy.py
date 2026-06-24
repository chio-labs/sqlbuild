"""Compiler planner reuse policy entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner.helpers.reuse.policy import decide_reuse_for_node as _decide
from sqlbuild.compiler.planner.models import ReusePolicyNodeFacts


def decide_reuse_for_node(facts: ReusePolicyNodeFacts) -> str:
    """Return the canonical planner reuse decision for one physical node."""

    return _decide(facts)
