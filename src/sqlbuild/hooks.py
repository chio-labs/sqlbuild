"""Public decorator API for SQLBuild model lifecycle hooks."""

from sqlbuild.python_nodes.decorators.helpers.hooks import get_hook_definition, hook
from sqlbuild.shared.models import HookDefinition

__all__ = ("HookDefinition", "get_hook_definition", "hook")
