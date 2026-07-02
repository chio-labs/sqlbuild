"""Playground command constants."""

from sqlbuild.cli.commands.helpers.playground.types import PlaygroundTemplate

PLAYGROUND_TEMPLATE_VALUES: tuple[str, ...] = tuple(
    template.value for template in PlaygroundTemplate
)
