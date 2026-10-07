from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile.models import DeclarationResolutionContext, MacroContext
from sqlbuild.python_nodes.models import SqlResourceRef


@dataclass(frozen=True)
class ContextStoreTokenTestCase:
    """Two macro contexts and whether their stored results may be shared."""

    description: str
    left: MacroContext
    right: MacroContext
    expected_equal: bool
    left_declarations: DeclarationResolutionContext | None = None
    right_declarations: DeclarationResolutionContext | None = None


@dataclass(frozen=True)
class ContextValueTestCase:
    """A macro context value and whether calls that may read it can be stored."""

    description: str
    context: MacroContext
    expected_stored: bool


@dataclass(frozen=True)
class CallClassStoreTextTestCase:
    """A call class's context and relations, compared with a plain class of the same macros."""

    description: str
    context_token: str | None
    prior_relations: tuple[SqlResourceRef, ...] | None
    expected_equal: bool


@dataclass(frozen=True)
class MacroStoreTokenTestCase:
    """A change to a loaded macro and whether its stored results stay valid."""

    description: str
    relative_path: Path
    raw_source: str
    expected_equal: bool


@dataclass(frozen=True)
class ModuleStampsRoundTripTestCase:
    """Module stamps encoded as store metadata and validated back."""

    description: str
    module_text: str
    expected_valid: bool


@dataclass(frozen=True)
class StoreEnvironmentTestCase:
    """A project edit and whether stored macro calls stay valid after it."""

    description: str
    edit: Callable[[Path], object]
    expected_unchanged: bool


@dataclass(frozen=True)
class StoreEnvironmentVariableTestCase:
    """An environment variable change and whether stored macro calls stay valid after it."""

    description: str
    name: str
    value: str
    expected_unchanged: bool


@dataclass(frozen=True)
class ModuleStampsTestCase:
    """Stored module stamps, a change to the module file, and whether they still validate."""

    description: str
    change: Callable[[Path], bytes]
    expected_valid: bool
