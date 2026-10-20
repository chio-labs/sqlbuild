"""Read the features Cargo resolves for each crate of one build."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.build_features.constants import (
    BUILD_DEPENDENCIES_DEPTH_OFFSET,
    BUILD_DEPENDENCIES_HEADING,
    HOST_SIDE,
    PROC_MACRO_MARKER,
    TARGET_SIDE,
    TREE_FIELD_SEPARATOR,
    TREE_FORMAT,
    TREE_GLYPHS,
    TREE_INDENT_WIDTH,
)
from scripts.build_features.models import ResolvedCrate


def run_cargo_tree(*, root: Path, selection: tuple[str, ...], target: str) -> str:
    """Return `cargo tree` output for the selected package on one target, without dedupe."""
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        (
            "cargo",
            "tree",
            "--locked",
            *selection,
            "--target",
            target,
            "--edges",
            "normal,build",
            "--format",
            TREE_FORMAT,
            "--prefix",
            "indent",
            "--no-dedupe",
            "--color",
            "never",
        ),
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def parse_cargo_tree(output: str) -> dict[ResolvedCrate, frozenset[str]]:
    """Map each crate to its resolved feature lists, with host compiles apart from target ones."""
    resolved: dict[ResolvedCrate, set[str]] = {}
    open_ancestors: tuple[tuple[float, bool], ...] = ()
    for line in output.splitlines():
        body: str = line.lstrip(TREE_GLYPHS)
        depth: int = (len(line) - len(body)) // TREE_INDENT_WIDTH
        if body.startswith(BUILD_DEPENDENCIES_HEADING):
            heading_depth: float = depth + BUILD_DEPENDENCIES_DEPTH_OFFSET
            open_ancestors = (
                *_enclosing(ancestors=open_ancestors, depth=heading_depth),
                (heading_depth, True),
            )
            continue
        if TREE_FIELD_SEPARATOR not in body:
            continue
        open_ancestors = _enclosing(ancestors=open_ancestors, depth=depth)
        package, features = body.split(TREE_FIELD_SEPARATOR, 1)
        host: bool = PROC_MACRO_MARKER in package or any(on_host for _, on_host in open_ancestors)
        name: str = " ".join(package.replace(PROC_MACRO_MARKER, "").split()[:2])
        crate: ResolvedCrate = ResolvedCrate(package=name, side=HOST_SIDE if host else TARGET_SIDE)
        resolved.setdefault(crate, set()).add(features.strip())
        open_ancestors = (*open_ancestors, (depth, host))
    return {crate: frozenset(features) for crate, features in resolved.items()}


def _enclosing(
    *, ancestors: tuple[tuple[float, bool], ...], depth: float
) -> tuple[tuple[float, bool], ...]:
    """Keep the ancestors above `depth`; a build-dependencies heading sits half a level down."""
    return tuple(ancestor for ancestor in ancestors if ancestor[0] < depth)
