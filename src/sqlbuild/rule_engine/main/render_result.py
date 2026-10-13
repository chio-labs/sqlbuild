"""Rules result formatting entrypoint."""

from sqlbuild._native import format_rules_result
from sqlbuild.rule_engine.models import RulesResult


def format_result(*, result: RulesResult, json_output: bool) -> str:
    """Format one rules result for the requested CLI surface."""

    return format_rules_result(result=result, json_output=json_output)
