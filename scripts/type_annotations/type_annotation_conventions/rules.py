"""Rule implementations for type annotation convention checks."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.type_annotations.type_annotation_conventions.constants import (
    DISCARDED_LOCAL_NAME,
    ENUM_BASE_CLASS_NAMES,
    EXEMPT_CLASS_ATTRIBUTE_NAMES,
    EXEMPT_MODULE_VARIABLE_NAMES,
    METHOD_RECEIVER_PARAMETER_NAMES,
)
from scripts.type_annotations.type_annotation_conventions.models import Violation


def parse_python_module(file_path: Path) -> ast.Module:
    """Parse a Python file into an AST module."""

    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def check_module(*, file_path: Path, module: ast.Module) -> list[Violation]:
    """Validate type annotation conventions for a parsed module."""

    visitor: _TypeAnnotationVisitor = _TypeAnnotationVisitor(file_path)
    visitor.visit(module)
    return visitor.violations


class _TypeAnnotationVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []
        self._class_depth = 0
        self._function_scopes: list[set[str]] = []

    def visit_Module(self, node: ast.Module) -> None:
        for statement in node.body:
            if isinstance(statement, (ast.Assign, ast.AugAssign)):
                self._check_module_assignment(statement)
                continue
            if isinstance(statement, ast.AnnAssign):
                self._record_annotated_assignment(statement.target)
                continue
            self.visit(statement)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_depth += 1
        is_enum_class: bool = _is_enum_class(node)
        try:
            for statement in node.body:
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    self.visit(statement)
                    continue
                if isinstance(statement, (ast.Assign, ast.AugAssign)):
                    if is_enum_class:
                        self.generic_visit(statement)
                        continue
                    self._check_class_assignment(statement)
                    continue
                if isinstance(statement, ast.AnnAssign):
                    if is_enum_class:
                        self.generic_visit(statement)
                        continue
                    self._record_annotated_assignment(statement.target)
                    continue
                self.visit(statement)
        finally:
            self._class_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._function_scopes:
            self._check_local_assignment(node)
            return
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._function_scopes:
            self._check_local_assignment(node)
            return
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._function_scopes:
            self._record_annotated_assignment(node.target)
            if node.value is not None:
                self.visit(node.value)
            return
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._check_function_signature(node)
        annotated_names: set[str] = self._annotated_parameter_names(node)
        self._function_scopes.append(annotated_names)
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._function_scopes.pop()

    def _check_function_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        positional_args: list[ast.arg] = [*node.args.posonlyargs, *node.args.args]
        exempt_parameter_name: str | None = None
        if (
            self._class_depth > 0
            and positional_args
            and positional_args[0].arg in METHOD_RECEIVER_PARAMETER_NAMES
        ):
            exempt_parameter_name = positional_args[0].arg

        for parameter in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]:
            if parameter.annotation is not None:
                continue
            if parameter.arg == exempt_parameter_name:
                continue
            self.violations.append(
                Violation(
                    code="TA001",
                    path=self.file_path,
                    line=parameter.lineno,
                    message=(f"function parameter '{parameter.arg}' must define a type annotation"),
                )
            )

        for parameter in [node.args.vararg, node.args.kwarg]:
            if parameter is None or parameter.annotation is not None:
                continue
            self.violations.append(
                Violation(
                    code="TA001",
                    path=self.file_path,
                    line=parameter.lineno,
                    message=(f"function parameter '{parameter.arg}' must define a type annotation"),
                )
            )

        if node.returns is None:
            self.violations.append(
                Violation(
                    code="TA002",
                    path=self.file_path,
                    line=node.lineno,
                    message=f"function '{node.name}' must define a return type annotation",
                )
            )

    def _annotated_parameter_names(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        names: set[str] = set()
        for parameter in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            node.args.vararg,
            node.args.kwarg,
        ]:
            if parameter is None:
                continue
            if parameter.annotation is not None or parameter.arg in METHOD_RECEIVER_PARAMETER_NAMES:
                names.add(parameter.arg)
        return names

    def _check_module_assignment(self, node: ast.Assign | ast.AugAssign) -> None:
        for target in _iter_simple_name_targets(node):
            if _is_exempt_module_name(target.id):
                continue
            self.violations.append(
                Violation(
                    code="TA003",
                    path=self.file_path,
                    line=target.lineno,
                    message=(f"module-level variable '{target.id}' must define a type annotation"),
                )
            )
        self.generic_visit(node)

    def _check_class_assignment(self, node: ast.Assign | ast.AugAssign) -> None:
        for target in _iter_simple_name_targets(node):
            if _is_exempt_class_name(target.id):
                continue
            self.violations.append(
                Violation(
                    code="TA004",
                    path=self.file_path,
                    line=target.lineno,
                    message=f"class attribute '{target.id}' must define a type annotation",
                )
            )
        self.generic_visit(node)

    def _check_local_assignment(self, node: ast.Assign | ast.AugAssign) -> None:
        current_scope: set[str] = self._function_scopes[-1]
        for target in _iter_simple_name_targets(node):
            if target.id == DISCARDED_LOCAL_NAME:
                continue
            if target.id in current_scope:
                continue
            self.violations.append(
                Violation(
                    code="TA005",
                    path=self.file_path,
                    line=target.lineno,
                    message=(
                        f"local variable '{target.id}' must define a type annotation "
                        "on first binding"
                    ),
                )
            )
            current_scope.add(target.id)
        self.generic_visit(node)

    def _record_annotated_assignment(self, target: ast.expr) -> None:
        if not self._function_scopes:
            return
        if isinstance(target, ast.Name):
            self._function_scopes[-1].add(target.id)


def _iter_simple_name_targets(node: ast.Assign | ast.AugAssign) -> list[ast.Name]:
    targets: list[ast.expr] = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target for target in targets if isinstance(target, ast.Name)]


def _is_exempt_module_name(name: str) -> bool:
    return name in EXEMPT_MODULE_VARIABLE_NAMES


def _is_exempt_class_name(name: str) -> bool:
    return name in EXEMPT_CLASS_ATTRIBUTE_NAMES


def _is_enum_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in ENUM_BASE_CLASS_NAMES:
            return True
        if isinstance(base, ast.Attribute) and base.attr in ENUM_BASE_CLASS_NAMES:
            return True
    return False
