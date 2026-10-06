"""Write the dense benchmark project, optionally with a custom Rule."""

from __future__ import annotations

from pathlib import Path

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from scripts.compiler_differential.constants import (
    CUSTOM_RULE_FILE,
    CUSTOM_RULE_SOURCE,
    CUSTOM_RULE_THRESHOLDS,
    PROJECT_CONFIG_FILE,
)


class DenseProject:
    """A dense compile benchmark project of one size."""

    def __init__(self, *, model_count: int, custom_rules: bool) -> None:
        self._model_count: int = model_count
        self._custom_rules: bool = custom_rules

    def write(self, project_dir: Path) -> None:
        """Write the project; with custom rules, add one Rule every model is checked by."""

        write_dense_compile_project(project_dir=project_dir, model_count=self._model_count)
        if not self._custom_rules:
            return
        rule_path: Path = project_dir / CUSTOM_RULE_FILE
        rule_path.parent.mkdir(parents=True, exist_ok=True)
        _ = rule_path.write_text(CUSTOM_RULE_SOURCE, encoding="utf-8", newline="\n")
        config_path: Path = project_dir / PROJECT_CONFIG_FILE
        _ = config_path.write_text(
            config_path.read_text(encoding="utf-8") + CUSTOM_RULE_THRESHOLDS,
            encoding="utf-8",
            newline="\n",
        )
