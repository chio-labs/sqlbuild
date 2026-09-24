"""Recognise forced overrides of contract methods, derived statically from the analysed source."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from scripts.dupscore._helpers.clones.filters import path_matches_any
from scripts.dupscore.constants import LANGUAGE_PYTHON, SOURCE_ROOT
from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import CloneUnit, ContractExemptionEntry

_ABSTRACT_DECORATOR: str = "abstractmethod"
_MODULE_SEPARATOR: str = "."
_PYTHON_SUFFIX: str = ".py"
_PACKAGE_INIT: str = "__init__.py"
_METHOD_NAME_PARTS: int = 2

type _FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type _ClassKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class _ClassInfo:
    bases: tuple[_ClassKey, ...]
    concrete: frozenset[str]
    abstract: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ContractScope:
    contract: _ClassKey
    method_names: frozenset[str]
    forbidden_owners: frozenset[_ClassKey]
    paths: tuple[str, ...]


def find_forced_overrides(
    *,
    repo_root: Path,
    entries: tuple[ContractExemptionEntry, ...],
    units: list[CloneUnit],
) -> tuple[bool, ...]:
    """Flag each unit that overrides a contract method it may not inherit from an ancestor."""

    exemptions: _ContractExemptions = _ContractExemptions(repo_root=repo_root, entries=entries)
    return tuple(exemptions.is_forced(unit) for unit in units)


class _ContractExemptions:
    def __init__(self, *, repo_root: Path, entries: tuple[ContractExemptionEntry, ...]) -> None:
        self._resolver: _ClassResolver = _ClassResolver(repo_root=repo_root)
        active: list[ContractExemptionEntry] = [
            entry for entry in entries if (repo_root / entry.contract_path).is_file()
        ]
        self._scopes: tuple[_ContractScope, ...] = tuple(self._scope(entry) for entry in active)

    def is_forced(self, unit: CloneUnit) -> bool:
        """Require a top-level class method under the paths that derives from the contract."""

        if unit.language != LANGUAGE_PYTHON:
            return False
        parts: list[str] = unit.name.split(_MODULE_SEPARATOR)
        if len(parts) != _METHOD_NAME_PARTS:
            return False
        class_name, method_name = parts
        for scope in self._scopes:
            if method_name not in scope.method_names:
                continue
            if not path_matches_any(path=unit.path, globs=scope.paths):
                continue
            if self._forced_in_scope(
                scope=scope, key=(unit.path, class_name), method_name=method_name
            ):
                return True
        return False

    def _forced_in_scope(self, *, scope: _ContractScope, key: _ClassKey, method_name: str) -> bool:
        order: tuple[_ClassKey, ...] = self._resolver.method_resolution_order(key)
        if scope.contract not in order:
            return False
        for ancestor in order[1:]:
            if method_name in self._resolver.info(ancestor).concrete:
                return ancestor in scope.forbidden_owners
        return True

    def _scope(self, entry: ContractExemptionEntry) -> _ContractScope:
        contract: _ClassKey = (entry.contract_path, entry.contract_class)
        forbidden: set[_ClassKey] = {contract}
        for key in (contract, *entry.forbidden_owners):
            if not self._resolver.exists(key):
                raise DupscoreConfigError(
                    f"contract_exemption class {key[0]}:{key[1]} was not found in the analysed "
                    "source"
                )
            forbidden.add(key)
        return _ContractScope(
            contract=contract,
            method_names=self._resolver.abstract_methods(contract),
            forbidden_owners=frozenset(forbidden),
            paths=entry.paths,
        )


class _ClassResolver:
    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root: Path = repo_root
        self._trees: dict[str, ast.Module | None] = {}
        self._infos: dict[_ClassKey, _ClassInfo] = {}
        self._orders: dict[_ClassKey, tuple[_ClassKey, ...]] = {}
        self._abstract: dict[_ClassKey, frozenset[str]] = {}

    def exists(self, key: _ClassKey) -> bool:
        tree: ast.Module | None = self._parse(key[0])
        return tree is not None and _find_class(tree=tree, name=key[1]) is not None

    def info(self, key: _ClassKey) -> _ClassInfo:
        if key not in self._infos:
            self._infos[key] = self._build_info(key)
        return self._infos[key]

    def abstract_methods(self, key: _ClassKey) -> frozenset[str]:
        """Mirror ``__abstractmethods__``: own abstract methods plus unoverridden inherited ones."""

        if key in self._abstract:
            return self._abstract[key]
        self._abstract[key] = frozenset()
        info: _ClassInfo = self.info(key)
        names: set[str] = set(info.abstract)
        for base in info.bases:
            names.update(self.abstract_methods(base) - info.concrete)
        self._abstract[key] = frozenset(names)
        return self._abstract[key]

    def method_resolution_order(self, key: _ClassKey) -> tuple[_ClassKey, ...]:
        """C3-linearise the statically resolvable bases, as ``type.__mro__`` would."""

        if key in self._orders:
            return self._orders[key]
        self._orders[key] = (key,)
        bases: tuple[_ClassKey, ...] = self.info(key).bases
        sequences: list[list[_ClassKey]] = [
            list(self.method_resolution_order(base)) for base in bases
        ]
        self._orders[key] = (key, *_c3_merge([*sequences, list(bases)]))
        return self._orders[key]

    def _parse(self, relative_path: str) -> ast.Module | None:
        if relative_path not in self._trees:
            try:
                source: str = (self._repo_root / relative_path).read_text(encoding="utf-8")
                self._trees[relative_path] = ast.parse(source)
            except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
                self._trees[relative_path] = None
        return self._trees[relative_path]

    def _build_info(self, key: _ClassKey) -> _ClassInfo:
        tree: ast.Module | None = self._parse(key[0])
        node: ast.ClassDef | None = None if tree is None else _find_class(tree=tree, name=key[1])
        if tree is None or node is None:
            return _ClassInfo(bases=(), concrete=frozenset(), abstract=frozenset())
        functions: list[_FunctionNode] = [
            item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        bases: list[_ClassKey] = []
        for base in node.bases:
            resolved: _ClassKey | None = self._resolve_base(tree=tree, importer=key[0], base=base)
            if resolved is not None:
                bases.append(resolved)
        return _ClassInfo(
            bases=tuple(bases),
            concrete=frozenset(item.name for item in functions if not _is_abstract(item)),
            abstract=frozenset(item.name for item in functions if _is_abstract(item)),
        )

    def _resolve_base(self, *, tree: ast.Module, importer: str, base: ast.expr) -> _ClassKey | None:
        if not isinstance(base, ast.Name):
            return None
        if _find_class(tree=tree, name=base.id) is not None:
            return (importer, base.id)
        for statement in tree.body:
            if not isinstance(statement, ast.ImportFrom):
                continue
            for alias in statement.names:
                if (alias.asname or alias.name) == base.id:
                    module_path: str | None = self._module_path(
                        importer=importer, module=statement.module, level=statement.level
                    )
                    return None if module_path is None else (module_path, alias.name)
        return None

    def _module_path(self, *, importer: str, module: str | None, level: int) -> str | None:
        if not module:
            return None
        parts: list[str] = module.split(_MODULE_SEPARATOR)
        if level:
            anchor: PurePosixPath = PurePosixPath(importer).parent
            for _ in range(level - 1):
                anchor = anchor.parent
            bases: list[PurePosixPath] = [anchor.joinpath(*parts)]
        else:
            bases = [PurePosixPath(SOURCE_ROOT).joinpath(*parts), PurePosixPath(*parts)]
        for base in bases:
            for candidate in (base.with_name(base.name + _PYTHON_SUFFIX), base / _PACKAGE_INIT):
                if (self._repo_root / candidate).is_file():
                    return candidate.as_posix()
        return None


def _c3_merge(sequences: list[list[_ClassKey]]) -> list[_ClassKey]:
    """Merge linearisations; an inconsistent hierarchy falls back to first-seen order."""

    merged: list[_ClassKey] = []
    pending: list[list[_ClassKey]] = [sequence for sequence in sequences if sequence]
    while pending:
        head: _ClassKey = _c3_head(pending)
        merged.append(head)
        remaining: list[list[_ClassKey]] = []
        for sequence in pending:
            rest: list[_ClassKey] = [item for item in sequence if item != head]
            if rest:
                remaining.append(rest)
        pending = remaining
    return merged


def _c3_head(pending: list[list[_ClassKey]]) -> _ClassKey:
    tails: set[_ClassKey] = set()
    for sequence in pending:
        tails.update(sequence[1:])
    for sequence in pending:
        if sequence[0] not in tails:
            return sequence[0]
    return pending[0][0]


def _find_class(*, tree: ast.Module, name: str) -> ast.ClassDef | None:
    for statement in tree.body:
        if isinstance(statement, ast.ClassDef) and statement.name == name:
            return statement
    return None


def _is_abstract(function: _FunctionNode) -> bool:
    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == _ABSTRACT_DECORATOR:
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == _ABSTRACT_DECORATOR:
            return True
    return False
