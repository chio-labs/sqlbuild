"""Runtime hermeticity audit hook for the custom-rule host."""

from __future__ import annotations

import functools
import importlib
import os
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import CodeType, FrameType, FunctionType, ModuleType

from sqlbuild.rule_engine._helpers.engine.hermeticity import allowed_custom_rule_import
from sqlbuild.rule_engine.classes.project_tree import ProjectTree
from sqlbuild.rule_engine.exceptions import NonHermeticRuleError

_IMPORT_EVENT: str = "import"
_OPEN_EVENT: str = "open"
_IMPORT_ENTRY_FUNCTION: str = "_find_and_load"
_FROZEN_IMPORT_PREFIX: str = "<frozen importlib."
_FILESYSTEM_EVENTS: dict[str, str] = {
    _OPEN_EVENT: "opening a file",
    "os.listdir": "listing a directory",
    "os.scandir": "listing a directory",
    "glob.glob": "listing a directory",
    "glob.glob/2": "listing a directory",
}
_PROCESS_EVENTS: dict[str, str] = {
    "os.exec": "running a command",
    "os.fork": "forking the process",
    "os.forkpty": "forking the process",
    "os.posix_spawn": "running a command",
    "os.spawn": "running a command",
    "os.startfile": "running a command",
    "os.system": "running a command",
    "subprocess.Popen": "running a command",
}
_PREFIX_EVENTS: tuple[tuple[str, str], ...] = (
    ("socket.", "network access"),
    ("ctypes.", "foreign function access"),
)
_GUARDED_EVENTS: frozenset[str] = frozenset({_IMPORT_EVENT, *_FILESYSTEM_EVENTS, *_PROCESS_EVENTS})
_GUARDED_PREFIXES: tuple[str, ...] = tuple(prefix for prefix, _ in _PREFIX_EVENTS)
_METADATA_ACTION: str = "reading file metadata"
_OS_METADATA_FUNCTIONS: tuple[str, ...] = ("access", "lstat", "readlink", "stat", "statvfs")
_PATH_METADATA_FUNCTIONS: tuple[str, ...] = (
    "exists",
    "getatime",
    "getctime",
    "getmtime",
    "getsize",
    "isdevdrive",
    "isdir",
    "isfile",
    "isjunction",
    "islink",
    "ismount",
    "lexists",
    "realpath",
    "samefile",
)
_OS_CAPABILITY_SETS: tuple[str, ...] = (
    "supports_dir_fd",
    "supports_effective_ids",
    "supports_fd",
    "supports_follow_symlinks",
)
_REMEDIATION: str = "read project inputs through ctx.project.tree and compiler facts"


class RuntimeGuard:
    """Audit hook rejecting untracked observations made while Rule code is on the stack."""

    def __init__(self, *, project_dir: Path) -> None:
        self._project_dir: Path = project_dir.resolve()
        self._rules_prefix: str = f"{self._project_dir / 'rules'}{os.sep}"
        self._importlib_prefix: str = f"{Path(importlib.__file__).resolve().parent}{os.sep}"
        self._mediated_codes: tuple[CodeType, ...] = _project_tree_codes()
        self._mediated_code_ids: frozenset[int] = frozenset(map(id, self._mediated_codes))
        self._rule_files: dict[str, bool] = {}
        self._metadata_scope: threading.local = threading.local()
        self.active_rule: str | None = None
        self.violation: NonHermeticRuleError | None = None

    def __call__(self, event: str, arguments: tuple[object, ...]) -> None:
        if event not in _GUARDED_EVENTS and not event.startswith(_GUARDED_PREFIXES):
            return
        frame: FrameType = sys._getframe(1)
        rule_frame: FrameType | None = (
            self._importing_rule_frame(frame)
            if event == _IMPORT_EVENT
            else self._responsible_rule_frame(frame)
        )
        if rule_frame is None:
            return
        if event == _IMPORT_EVENT and allowed_custom_rule_import(str(arguments[0])):
            return
        self._reject(rule_frame=rule_frame, action=_action(event=event, arguments=arguments))

    def guard_filesystem_metadata(self) -> None:
        """Route unaudited os and os.path metadata calls through the Rule attribution check."""

        self._wrap(module=os, names=_OS_METADATA_FUNCTIONS)
        self._wrap(module=os.path, names=_PATH_METADATA_FUNCTIONS)

    def _wrap(self, *, module: ModuleType, names: tuple[str, ...]) -> None:
        for name in names:
            original: object = getattr(module, name, None)
            if callable(original):
                guarded: Callable[..., object] = self._guarded(original)
                setattr(module, name, guarded)
                for capability in _OS_CAPABILITY_SETS:
                    supported: set[object] = getattr(os, capability)
                    if original in supported:
                        supported.add(guarded)

    def _guarded(self, function: Callable[..., object]) -> Callable[..., object]:
        guarded: functools.partial[object] = functools.partial(
            self._call_metadata, guarded_function=function
        )
        return functools.update_wrapper(guarded, function)

    def _call_metadata(
        self, *arguments: object, guarded_function: Callable[..., object], **keywords: object
    ) -> object:
        function: Callable[..., object] = guarded_function
        if getattr(self._metadata_scope, "trusted", False):
            return function(*arguments, **keywords)
        paths: tuple[object, ...] = tuple(map(_plain_path, arguments))
        named: dict[str, object] = {key: _plain_path(value) for key, value in keywords.items()}
        rule_frame: FrameType | None = self._responsible_rule_frame(sys._getframe(1))
        if rule_frame is not None:
            target: str = f" for {paths[0]!r}" if paths else ""
            self._reject(rule_frame=rule_frame, action=f"{_METADATA_ACTION}{target}")
        self._metadata_scope.trusted = True
        try:
            return function(*paths, **named)
        finally:
            self._metadata_scope.trusted = False

    @contextmanager
    def rule(self, code: str) -> Iterator[None]:
        """Attribute violations to one Rule and surface them even when Rule code catches them."""

        self.active_rule = code
        try:
            yield
        except Exception:
            self.raise_violation()
            raise
        finally:
            self.active_rule = None
        self.raise_violation()

    def raise_violation(self) -> None:
        """Raise the first recorded violation, if any."""

        if self.violation is not None:
            raise self.violation

    def _reject(self, *, rule_frame: FrameType, action: str) -> None:
        filename: Path = Path(rule_frame.f_code.co_filename)
        location: str = (
            filename.relative_to(self._project_dir).as_posix()
            if filename.is_relative_to(self._project_dir)
            else filename.as_posix()
        )
        owner: str = "" if self.active_rule is None else f" {self.active_rule}"
        error: NonHermeticRuleError = NonHermeticRuleError(
            f"non-hermetic custom rule{owner} at {location}:{rule_frame.f_lineno}: "
            f"{action} is not allowed; {_REMEDIATION}"
        )
        if self.violation is None:
            self.violation = error
        raise error

    def _responsible_rule_frame(self, frame: FrameType | None) -> FrameType | None:
        """Return the innermost Rule frame not shielded by module import or a mediated read."""

        rule_files: dict[str, bool] = self._rule_files
        mediated: frozenset[int] = self._mediated_code_ids
        while frame is not None:
            code: CodeType = frame.f_code
            is_rule: bool | None = rule_files.get(code.co_filename)
            if is_rule is None:
                is_rule = self._is_rule_file(code.co_filename)
            if is_rule:
                return frame
            if id(code) in mediated or (
                code.co_name == _IMPORT_ENTRY_FUNCTION
                and self._is_import_machinery(code.co_filename)
            ):
                return None
            frame = frame.f_back
        return None

    def _importing_rule_frame(self, frame: FrameType | None) -> FrameType | None:
        while frame is not None and self._is_import_machinery(frame.f_code.co_filename):
            frame = frame.f_back
        if frame is None or not self._is_rule_file(frame.f_code.co_filename):
            return None
        return frame

    def _is_rule_file(self, filename: str) -> bool:
        cached: bool | None = self._rule_files.get(filename)
        if cached is None:
            cached = filename.startswith(self._rules_prefix)
            self._rule_files[filename] = cached
        return cached

    def _is_import_machinery(self, filename: str) -> bool:
        return filename.startswith((_FROZEN_IMPORT_PREFIX, self._importlib_prefix))


def _project_tree_codes() -> tuple[CodeType, ...]:
    codes: list[CodeType] = []
    for value in vars(ProjectTree).values():
        member: object = getattr(value, "__func__", value)
        if isinstance(member, FunctionType):
            codes.append(member.__code__)
    return tuple(codes)


def _plain_path(value: object) -> object:
    return os.fspath(value) if isinstance(value, os.PathLike) else value


def _action(*, event: str, arguments: tuple[object, ...]) -> str:
    if event == _OPEN_EVENT and arguments:
        return f"opening {arguments[0]!r}"
    if event == _IMPORT_EVENT and arguments:
        return f"import {arguments[0]!r}"
    action: str | None = _FILESYSTEM_EVENTS.get(event) or _PROCESS_EVENTS.get(event)
    if action is not None:
        return action
    return next(
        (prefix_action for prefix, prefix_action in _PREFIX_EVENTS if event.startswith(prefix)),
        event,
    )
