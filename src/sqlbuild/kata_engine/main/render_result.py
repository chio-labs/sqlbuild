"""Kata result formatting entrypoint."""

from sqlbuild.kata_engine._helpers.guidance.presentation import (
    format_result_json,
    format_result_text,
)
from sqlbuild.kata_engine.models import KataResult


def format_result(*, result: KataResult, json_output: bool) -> str:
    """Format one kata result for the requested CLI surface."""

    if json_output:
        return format_result_json(result=result)
    return format_result_text(result=result)
