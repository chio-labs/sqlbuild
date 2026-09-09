"""Rule formatting entrypoint."""

from sqlbuild.rule_engine._helpers.guidance.presentation import format_rule_text
from sqlbuild.rule_engine.models import Rule, RulesConfig


def format_rule(*, rule: Rule, config: RulesConfig | None = None) -> str:
    """Format one rule for inspection."""

    return format_rule_text(rule=rule, config=config)
