from __future__ import annotations

from scripts.dupscore._helpers.clones.tokens import build_clone_unit
from scripts.dupscore.models import CloneUnit


def diverging_unit(*, name: str, shared_tokens: int, differing_tokens: int) -> CloneUnit:
    """Build a unit whose stream starts with common tokens and ends with side-specific ones."""

    tokens: list[str] = [f"shared{index}" for index in range(shared_tokens)]
    tokens.extend(f"{name}{index}" for index in range(differing_tokens))
    return build_clone_unit(
        language="python",
        path=f"src/sqlbuild/{name}.py",
        name=name,
        start_line=1,
        end_line=len(tokens),
        normalized=tokens,
        concrete=tokens,
    )
