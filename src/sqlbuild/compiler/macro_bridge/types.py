"""Macro bridge type aliases."""

from __future__ import annotations

from sqlbuild.python_nodes.models import SqlResourceRef

type MacroCallEvent = tuple[int, str, str]
type MacroCallRecord = tuple[str, tuple[SqlResourceRef, ...], tuple[MacroCallEvent, ...]]
type ModuleStamp = tuple[int, int]
