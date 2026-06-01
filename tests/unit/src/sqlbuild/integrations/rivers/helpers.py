from __future__ import annotations

from dataclasses import dataclass


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
