from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlbuild.integrations.rivers.classes.sqlbuild_rivers_translator import (
    SqlBuildRiversTranslator,
)


@dataclass(frozen=True)
class FakeRiversAssetDep:
    name: str


@dataclass(frozen=True)
class FakeRiversAssetDef:
    name: str
    tags: list[str]
    kinds: list[str]
    group: str | None
    metadata: dict[str, str]
    deps: list[FakeRiversAssetDep]

    @staticmethod
    def dep(name: str) -> FakeRiversAssetDep:
        return FakeRiversAssetDep(name=name)


@dataclass(frozen=True)
class FakeRiversModule:
    AssetDef: type[FakeRiversAssetDef] = FakeRiversAssetDef


class RecordingRiversTranslator(SqlBuildRiversTranslator):
    """Default Rivers translator that records named nodes by id and project-name presence."""

    def __init__(self) -> None:
        self.named_nodes: dict[tuple[str, bool], list[Mapping[str, Any]]] = {}

    def get_asset_name(self, node: Mapping[str, Any]) -> str:
        self.named_nodes.setdefault((str(node["id"]), "project_name" in node), []).append(node)
        return super().get_asset_name(node)
