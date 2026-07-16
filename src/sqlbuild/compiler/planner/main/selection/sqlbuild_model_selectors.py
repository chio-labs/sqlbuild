"""Public SQLBuild model selector resolution entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject


def resolve_sqlbuild_model_selector_names(
    *, project: CompiledProject, term: str
) -> tuple[tuple[str, ...], str | None]:
    """Resolve one SQLBuild-owned model selector core to names and path translation."""

    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    if term in models_by_name:
        return (term,), None
    if term.startswith("tag:"):
        tag: str = term.removeprefix("tag:")
        names: list[str] = []
        for model in project.models:
            raw_tags: object = model.config.values.get("tags")
            tags: tuple[str, ...] = ()
            if isinstance(raw_tags, tuple):
                tags = tuple(str(item) for item in raw_tags)
            elif isinstance(raw_tags, list):
                tags = tuple(str(item) for item in raw_tags)
            if tag in tags:
                names.append(model.name)
        return tuple(names), None
    if term.startswith("path:"):
        raw_path: str = term.removeprefix("path:")
        translated_path: str = raw_path.replace("\\", "/")
        names = [
            model.name
            for model in project.models
            if (model_path := model.relative_path.parent.as_posix()) == translated_path
            or model_path.startswith(f"{translated_path}/")
        ]
        return tuple(names), f"path:{translated_path}" if translated_path != raw_path else None
    return (), None
