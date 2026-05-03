"""Compile command models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WrittenTarget:
    """Result of writing compiled output to target/."""

    model_count: int
    seed_count: int
    audit_count: int
    test_count: int
    target_dir: Path

    def summary_line(self) -> str:
        """Build a human-readable summary line."""

        parts: list[str] = []
        if self.model_count:
            model_label: str = "model" if self.model_count == 1 else "models"
            parts.append(f"{self.model_count} {model_label}")
        if self.seed_count:
            seed_label: str = "seed" if self.seed_count == 1 else "seeds"
            parts.append(f"{self.seed_count} {seed_label}")
        if self.audit_count:
            audit_label: str = "audit" if self.audit_count == 1 else "audits"
            parts.append(f"{self.audit_count} {audit_label}")
        if self.test_count:
            test_label: str = "test" if self.test_count == 1 else "tests"
            parts.append(f"{self.test_count} {test_label}")
        if not parts:
            return "Compiled 0 resources"
        return f"Compiled {', '.join(parts)}"
