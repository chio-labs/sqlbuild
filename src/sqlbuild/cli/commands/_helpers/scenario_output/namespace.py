"""Namespace attribution for scenario lifecycle progress."""

from __future__ import annotations

from sqlbuild.cli.commands.models import ScenarioRunOutputContext


def scenario_activity_message(*, activity: str, context: ScenarioRunOutputContext) -> str:
    """Label scenario work with the effective namespace and its source."""
    return (
        f"{activity} (namespace: {context.namespace.value or '(unset)'}; "
        f"source: {context.namespace.source})"
    )


def write_namespace_completion(*, context: ScenarioRunOutputContext, succeeded: bool) -> None:
    """Emit the explicit terminal state for the namespaced run."""
    message: str = scenario_activity_message(
        activity="Scenario execution complete" if succeeded else "Scenario execution failed",
        context=context,
    )
    context.progress_stream.write(f"{message}\n")
    context.progress_stream.flush()
