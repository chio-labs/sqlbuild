"""Kata rule formatting entrypoint."""

from sqlbuild.kata_engine._helpers.guidance.presentation import format_rule_text
from sqlbuild.kata_engine.models import KataConfig, KataRule


def format_rule(*, rule: KataRule, config: KataConfig | None = None) -> str:
    """Format one kata rule for inspection."""

    return format_rule_text(rule=rule, config=config)
