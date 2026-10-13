"""Resolve module paths found in native source against the importable Python package."""

from __future__ import annotations

import importlib

from scripts.native_module_paths.models import ModulePathReference


def unresolved_reference_error(*, reference: ModulePathReference) -> str | None:
    """Why the reference does not resolve to a module, module attribute or class member."""
    target: object | None = _resolved(path=reference.path)
    if target is None:
        return f"{reference.location}: '{reference.path}' is not an importable module or attribute."
    if reference.attribute is not None and not hasattr(target, reference.attribute):
        return f"{reference.location}: '{reference.path}' has no attribute '{reference.attribute}'."
    return None


def _resolved(*, path: str) -> object | None:
    """The longest importable module prefix of `path`, then its remaining attributes."""
    parts: list[str] = path.split(".")
    for split in range(len(parts), 0, -1):
        try:
            target: object = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        for attribute in parts[split:]:
            if not hasattr(target, attribute):
                return None
            target = getattr(target, attribute)
        return target
    return None
