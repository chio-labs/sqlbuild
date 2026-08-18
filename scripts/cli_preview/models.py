"""CLI preview models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewScene:
    """One reproducible production-CLI preview workflow."""

    name: str
    description: str
    command: tuple[str, ...]
    template: str = "waffle_shop"
    setup_commands: tuple[tuple[str, ...], ...] = ()
    post_mutation_commands: tuple[tuple[str, ...], ...] = ()
    mutate_payments: bool = False
    mutate_virtual_model: bool = False
    enable_janitor: bool = False
    expected_return_codes: tuple[int, ...] = (0,)
