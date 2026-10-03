"""Locate one named entry in an authored YAML declaration file."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.yml.entry_lines import yaml_entry_lines


def yaml_entry_line(*, contents: str, name: str) -> int | None:
    """Return the 1-based line of the outermost `- name: <name>` entry, if present."""

    return yaml_entry_lines(contents).get(name)
