"""Rules result formatting entrypoint."""

from sqlbuild.rule_engine._helpers.guidance.presentation import (
    format_result_json,
    format_result_text,
)
from sqlbuild.rule_engine.models import RulesResult


def format_result(*, result: RulesResult, json_output: bool) -> str:
    """Format one rules result for the requested CLI surface."""

    if json_output:
        return format_result_json(result=result)
    return format_result_text(result=result)
