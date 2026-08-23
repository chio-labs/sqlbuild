"""Kata rule formatting entrypoint."""

from sqlbuild.kata_engine._helpers.guidance.presentation import format_rule_text
from sqlbuild.kata_engine.models import KataRule


def format_rule(*, rule: KataRule) -> str:
    """Format one kata rule for inspection."""

    return format_rule_text(rule=rule)
