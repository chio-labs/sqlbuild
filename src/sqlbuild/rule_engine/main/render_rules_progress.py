"""Rules phase completion line entrypoint."""

from sqlbuild.rule_engine.main.render_skipped_rules import format_skipped_type_proof_rules
from sqlbuild.rule_engine.models import RulesRunResult


def format_rules_progress(
    *, elapsed_seconds: float, result: RulesRunResult, note_skipped_rules: bool = False
) -> str:
    """Report the rules phase wall time first, then built-in and custom rule time."""

    message: str = (
        f"Evaluated rules. ({elapsed_seconds:.2f}s; built-in {result.built_in_ms / 1000:.2f}s, "
        f"custom {result.custom_ms / 1000:.2f}s)"
    )
    skipped_rules_note: str | None = (
        format_skipped_type_proof_rules(codes=result.skipped_type_proof_rules)
        if note_skipped_rules
        else None
    )
    return message if skipped_rules_note is None else f"{message}; {skipped_rules_note}"
