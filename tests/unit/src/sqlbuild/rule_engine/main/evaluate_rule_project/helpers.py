"""A project with a `rules/` package whose rule imports a shared helper."""

import importlib.util
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

PROJECT_RULE_FILES: dict[str, str] = {
    "sqlbuild_project.toml": 'name = "orders"\nadapter = "duckdb"\n',
    "rules/_helpers/naming.py": (
        'def has_layer_prefix(name: str) -> bool:\n    return name.startswith(("stg_", "fct_"))\n'
    ),
    "rules/model_names.py": (
        "from rules._helpers.naming import has_layer_prefix\n"
        "from sqlbuild.rules import Finding, Model, RuleContext, rule\n\n\n"
        "@rule(\n"
        '    code="XSQBRNAME001",\n'
        '    message="Model names start with their layer",\n'
        '    remediation="Rename the model with a stg_ or fct_ prefix.",\n'
        ")\n"
        "def model_names(*, model: Model, ctx: RuleContext) -> list[Finding]:\n"
        "    return [ctx.finding(subject=model)] * int(not has_layer_prefix(model.name))\n"
    ),
}


def load_project_rule(*, root: Path, files: dict[str, str]) -> object:
    """Write a project with a `rules/` package and import its `model_names` rule from the file."""

    for relative_path, contents in files.items():
        path: Path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    sys.path.insert(0, str(root))
    try:
        spec: ModuleSpec | None = importlib.util.spec_from_file_location(
            "rules.model_names", root / "rules" / "model_names.py"
        )
        assert spec is not None and spec.loader is not None
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(root))
    return module.model_names
