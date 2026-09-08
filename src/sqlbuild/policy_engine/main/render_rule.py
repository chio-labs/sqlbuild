"""Policy rule formatting entrypoint."""

from sqlbuild.policy_engine._helpers.guidance.presentation import format_rule_text
from sqlbuild.policy_engine.models import PolicyConfig, PolicyRule


def format_rule(*, rule: PolicyRule, config: PolicyConfig | None = None) -> str:
    """Format one policy rule for inspection."""

    return format_rule_text(rule=rule, config=config)
