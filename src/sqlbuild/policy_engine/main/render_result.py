"""Policy result formatting entrypoint."""

from sqlbuild.policy_engine._helpers.guidance.presentation import (
    format_result_json,
    format_result_text,
)
from sqlbuild.policy_engine.models import PolicyResult


def format_result(*, result: PolicyResult, json_output: bool) -> str:
    """Format one policy result for the requested CLI surface."""

    if json_output:
        return format_result_json(result=result)
    return format_result_text(result=result)
