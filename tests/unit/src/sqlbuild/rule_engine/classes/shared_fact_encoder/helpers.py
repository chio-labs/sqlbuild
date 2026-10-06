from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSource
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSourceFile
from sqlbuild.rule_engine.classes.rule_context import RuleFactViews, build_rule_fact_views
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project

SOURCES_CONTENTS: str = "sources:\n  - name: raw_orders\n  - name: raw_customers\n"
SOURCE_NAMES: tuple[str, ...] = ("raw_orders", "raw_customers")
_SOURCES_PATH: Path = Path("sources/raw.yml")


def shared_file_views(*, tmp_path: Path, names: tuple[str, ...], contents: str) -> RuleFactViews:
    """Return Rule fact views over sources that share one declaration-file object."""

    declared: DiscoveredSourceFile = _source_file(tmp_path=tmp_path, names=names, contents=contents)
    return _views(tmp_path=tmp_path, files=tuple(declared for _ in names), names=names)


def copied_file_views(*, tmp_path: Path, names: tuple[str, ...], contents: str) -> RuleFactViews:
    """Return Rule fact views over sources that each hold an equal copy of their file."""

    files: tuple[DiscoveredSourceFile, ...] = tuple(
        _source_file(tmp_path=tmp_path, names=names, contents=contents) for _ in names
    )
    return _views(tmp_path=tmp_path, files=files, names=names)


def _source_file(*, tmp_path: Path, names: tuple[str, ...], contents: str) -> DiscoveredSourceFile:
    return DiscoveredSourceFile(
        file_path=tmp_path / _SOURCES_PATH,
        relative_path=_SOURCES_PATH,
        contents=contents,
        source_entries=tuple(SourceEntry(name=name) for name in names),
    )


def _views(
    *, tmp_path: Path, files: tuple[DiscoveredSourceFile, ...], names: tuple[str, ...]
) -> RuleFactViews:
    sources: tuple[CompiledSource, ...] = tuple(
        CompiledSource(
            key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name),
            deps=(),
            name=name,
            source_entry=SourceEntry(name=name),
            source_file=declared,
        )
        for name, declared in zip(names, files, strict=True)
    )
    project: CompiledProject = replace(
        build_project(
            name="orders", relative_path="models/orders.sql", sql="SELECT 1", config_values={}
        ),
        sources=sources,
    )
    return build_rule_fact_views(project=project, project_dir=tmp_path, dialect="duckdb")
