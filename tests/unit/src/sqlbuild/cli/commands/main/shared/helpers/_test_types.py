from dataclasses import dataclass, field

from sqlbuild.compiler.planner.models import PlanOutput


@dataclass(frozen=True)
class JsonOutputTestCase:
    description: str
    plan_output: PlanOutput
    expected_keys: tuple[str, ...]
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
