"""Edit a SQL model file's MODEL header and query as text."""

from __future__ import annotations

import re

from scripts.planner_differential.models import ModelFile

_HEADER_START: re.Pattern[str] = re.compile(r"^\s*MODEL\s*\(", re.MULTILINE)
_HEADER_END: re.Pattern[str] = re.compile(r"^[ \t]*\)[ \t]*;[ \t]*$", re.MULTILINE)
_STATEMENT_SEPARATOR: str = ";"
_INLINE_HEADER: re.Pattern[str] = re.compile(r"\A\s*MODEL\s*\((?P<body>[^;]*)\)\s*;")


def split_model_file(text: str) -> ModelFile | None:
    """Split a model file into its MODEL header and one-statement query, or None."""

    header: str = ""
    start: re.Match[str] | None = _HEADER_START.match(text)
    if start is not None:
        end: re.Match[str] | None = _HEADER_END.search(text, start.end())
        inline: re.Match[str] | None = _INLINE_HEADER.match(text)
        if end is not None:
            header = text[: end.end()]
        elif inline is not None:
            header = inline.group(0)
        else:
            return None
    query: str = text[len(header) :].strip().rstrip(";").strip()
    if not query or _STATEMENT_SEPARATOR in query or _HEADER_START.match(query):
        return None
    return ModelFile(header=header, query=query)


def join_model_file(model_file: ModelFile) -> str:
    """Return the file text for a header and query."""

    prefix: str = f"{model_file.header}\n\n" if model_file.header else ""
    return f"{prefix}{model_file.query}\n"


def add_header_property(*, header: str, line: str) -> str:
    """Insert one `name value,` property at the start of the MODEL header."""

    if not header:
        return f"MODEL (\n  {line}\n);"
    start: re.Match[str] | None = _HEADER_START.match(header)
    if start is None:
        return header
    return f"{header[: start.end()]}\n  {line}{header[start.end() :]}"
