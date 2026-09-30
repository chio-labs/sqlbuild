"""Token-exact MODEL header edits for renamed models and columns."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.main._model_header_spans import get_model_header_spans
from sqlbuild.compiler.discovery.models import ModelHeaderSpans
from sqlbuild.compiler.refactoring._helpers.text.sql_sites import embedded_ref_spans
from sqlbuild.compiler.refactoring._helpers.text.text_edits import text_edit, whole_word_offsets
from sqlbuild.compiler.refactoring.constants import (
    COLUMN_VALUED_CONFIG_KEYS,
    COLUMNS_KEY,
    CURSOR_INPUTS_KEY,
    HEADER_CLOSERS,
    HEADER_DESCRIPTION_KEY,
    HEADER_INDENT,
    HEADER_KEY_AND_VALUE_TOKENS,
    HEADER_OPEN_PAREN,
    HEADER_OPENERS,
    HEADER_SEPARATOR,
    IDENTIFIER_PATTERN,
    NATIVE_HEADER_TOKEN_KINDS,
    PARENTHESIZED_EMPTY_TOKENS,
    REF_FUNCTION,
    RELATIONSHIPS_AUDIT,
    RELATIONSHIPS_FIELD_KEY,
    RELATIONSHIPS_TO_KEY,
)
from sqlbuild.compiler.refactoring.models import (
    HeaderEntry,
    HeaderToken,
    RelationshipTokens,
    TextEdit,
)
from sqlbuild.compiler.refactoring.types import EditKind, HeaderTokenKind
from sqlbuild.lint.main.quoted_value_end import quoted_value_end

_VALUE_KINDS: frozenset[HeaderTokenKind] = frozenset({HeaderTokenKind.WORD, HeaderTokenKind.STRING})


def header_tokens(*, contents: str) -> tuple[HeaderToken, ...] | None:
    """Tokenize the MODEL header body in file offsets, or None without a header."""

    spans: ModelHeaderSpans = get_model_header_spans(contents=contents)
    if spans.body is None:
        return None
    return span_tokens(contents=contents, span=spans.body)


def span_tokens(*, contents: str, span: tuple[int, int]) -> tuple[HeaderToken, ...]:
    """Tokenize one declaration header body in file offsets."""

    body_start: int = span[0]
    body: str = contents[span[0] : span[1]]
    tokens: list[HeaderToken] = []
    depth: int = 0
    raw_kind: int
    value: str
    position: int
    for raw_kind, value, position in _native.tokenize_model_header(body):
        kind: HeaderTokenKind = NATIVE_HEADER_TOKEN_KINDS[raw_kind]
        if kind == HeaderTokenKind.END:
            continue
        start: int = body_start + position
        end: int = _token_end(contents=contents, kind=kind, value=value, start=start)
        if kind == HeaderTokenKind.SYMBOL and value in HEADER_CLOSERS:
            depth -= 1
        tokens.append(HeaderToken(kind=kind, value=value, start=start, end=end, depth=depth))
        if kind == HeaderTokenKind.SYMBOL and value in HEADER_OPENERS:
            depth += 1
    return tuple(tokens)


def header_entries(*, tokens: tuple[HeaderToken, ...]) -> tuple[HeaderEntry, ...]:
    """Split header tokens into top-level entries keyed by their first word."""

    return tuple(
        HeaderEntry(key=first.value, tokens=(first, *rest))
        for first, rest in _nested_entries(tokens=tokens, depth=0)
        if first.kind == HeaderTokenKind.WORD
    )


def rename_value_token(
    *, contents: str, token: HeaderToken, new_value: str, kind: EditKind
) -> TextEdit:
    """Replace one word or string value, keeping string quoting."""

    replacement: str = (
        new_value
        if token.kind == HeaderTokenKind.WORD
        else f"{contents[token.start]}{new_value}{contents[token.start]}"
    )
    return text_edit(
        text=contents,
        start=token.start,
        end=token.end,
        replacement=replacement,
        kind=kind,
    )


def is_value(*, token: HeaderToken, value: str) -> bool:
    """Return whether a word or string token spells a name, ignoring case."""

    return token.kind in _VALUE_KINDS and token.value.lower() == value.lower()


def cursor_input_tokens(
    *, tokens: tuple[HeaderToken, ...]
) -> tuple[tuple[HeaderToken, tuple[HeaderToken, ...]], ...]:
    """Return (input name token, value tokens) for every cursor_inputs entry."""

    entry: HeaderEntry
    for entry in header_entries(tokens=tokens):
        if entry.key != CURSOR_INPUTS_KEY:
            continue
        return _nested_entries(tokens=entry.tokens[1:], depth=1)
    return ()


def relationship_tokens(*, tokens: tuple[HeaderToken, ...]) -> tuple[RelationshipTokens, ...]:
    """Return the target and field value tokens of every relationships audit."""

    found: list[RelationshipTokens] = []
    index: int
    token: HeaderToken
    for index, token in enumerate(tokens):
        if not (
            token.kind == HeaderTokenKind.WORD
            and token.value == RELATIONSHIPS_AUDIT
            and index + 1 < len(tokens)
            and tokens[index + 1].value == HEADER_OPEN_PAREN
        ):
            continue
        depth: int = tokens[index + 1].depth + 1
        values: dict[str, int] = {}
        cursor: int = index + 2
        while cursor < len(tokens) and tokens[cursor].depth >= depth:
            candidate: HeaderToken = tokens[cursor]
            if (
                candidate.depth == depth
                and candidate.kind == HeaderTokenKind.WORD
                and candidate.value in {RELATIONSHIPS_TO_KEY, RELATIONSHIPS_FIELD_KEY}
                and cursor + 1 < len(tokens)
            ):
                values[candidate.value] = cursor + 1
            cursor += 1
        found.append(
            _relationship(
                tokens=tokens,
                to_index=values.get(RELATIONSHIPS_TO_KEY),
                field_index=values.get(RELATIONSHIPS_FIELD_KEY),
            )
        )
    return tuple(found)


def column_config_edits(
    *, contents: str, tokens: tuple[HeaderToken, ...], old: str, new: str
) -> tuple[TextEdit, ...]:
    """Rename a column in column-valued config such as cursor or unique_key."""

    edits: list[TextEdit] = []
    entry: HeaderEntry
    for entry in header_entries(tokens=tokens):
        if entry.key not in COLUMN_VALUED_CONFIG_KEYS:
            continue
        token: HeaderToken
        for token in entry.tokens[1:]:
            if is_value(token=token, value=old):
                edits.append(
                    rename_value_token(
                        contents=contents, token=token, new_value=new, kind=EditKind.HEADER
                    )
                )
    return tuple(edits)


def column_entry_edits(
    *, contents: str, tokens: tuple[HeaderToken, ...], old: str, new: str, migrate: bool
) -> tuple[TextEdit, ...] | None:
    """Rename a `columns` entry and add `migrate_from` if needed; None without an entry."""

    entry: HeaderEntry
    for entry in header_entries(tokens=tokens):
        if entry.key != COLUMNS_KEY:
            continue
        nested: tuple[tuple[HeaderToken, tuple[HeaderToken, ...]], ...] = _nested_entries(
            tokens=entry.tokens[1:], depth=1
        )
        name_token: HeaderToken
        values: tuple[HeaderToken, ...]
        for name_token, values in nested:
            if not is_value(token=name_token, value=old):
                continue
            edits: list[TextEdit] = [
                rename_value_token(
                    contents=contents, token=name_token, new_value=new, kind=EditKind.HEADER
                )
            ]
            if migrate:
                edits.append(
                    _column_migration_edit(
                        contents=contents, name=name_token, values=values, old=old
                    )
                )
            return tuple(edits)
    return None


def add_column_entry_edit(
    *, contents: str, tokens: tuple[HeaderToken, ...], new: str, old: str
) -> TextEdit | None:
    """Declare `new (migrate_from old)` in the columns block, creating it when absent."""

    declaration: str = f"{new} (migrate_from {old})"
    entry: HeaderEntry
    for entry in header_entries(tokens=tokens):
        if entry.key != COLUMNS_KEY or len(entry.tokens) < HEADER_KEY_AND_VALUE_TOKENS:
            continue
        opener: HeaderToken = entry.tokens[1]
        indentation: str = _line_indent(contents=contents, offset=entry.tokens[0].start)
        return text_edit(
            text=contents,
            start=opener.end,
            end=opener.end,
            replacement=f"\n{indentation}{HEADER_INDENT}{declaration},",
            kind=EditKind.MIGRATION,
            before="",
            after=declaration,
        )
    return insert_header_entry_edit(
        contents=contents, entry=f"columns ({declaration})", display=declaration
    )


def insert_header_entry_edit(*, contents: str, entry: str, display: str) -> TextEdit | None:
    """Insert one top-level entry as the first MODEL header line."""

    spans: ModelHeaderSpans = get_model_header_spans(contents=contents)
    if spans.body is None:
        return None
    start: int = spans.body[0]
    body: str = contents[spans.body[0] : spans.body[1]]
    if body.startswith("\n"):
        line_end: int = body.find("\n", 1)
        first_line: str = body[1:] if line_end < 0 else body[1:line_end]
        indentation: str = first_line[: len(first_line) - len(first_line.lstrip())] or HEADER_INDENT
        replacement: str = f"\n{indentation}{entry},"
    elif body.strip():
        replacement = f"{entry}, "
    else:
        replacement = f"\n{HEADER_INDENT}{entry},\n"
    return text_edit(
        text=contents,
        start=start,
        end=start,
        replacement=replacement,
        kind=EditKind.MIGRATION,
        before="",
        after=display,
    )


def unhandled_word_offsets(
    *, contents: str, tokens: tuple[HeaderToken, ...], word: str, handled: frozenset[int]
) -> tuple[int, ...]:
    """Return header offsets that still mention a word outside descriptions."""

    offsets: list[int] = []
    previous: HeaderToken | None = None
    token: HeaderToken
    for token in tokens:
        described: bool = previous is not None and previous.value == HEADER_DESCRIPTION_KEY
        previous = token
        if token.kind == HeaderTokenKind.SYMBOL or described or token.start in handled:
            continue
        text: str = contents[token.start : token.end]
        offsets.extend(token.start + offset for offset in whole_word_offsets(text=text, word=word))
    return tuple(offsets)


def model_name_header_edits(*, contents: str, old: str, new: str) -> tuple[TextEdit, ...]:
    """Rename a model in cursor_inputs keys, bare relationships targets, and quoted SQL."""

    tokens: tuple[HeaderToken, ...] | None = header_tokens(contents=contents)
    if tokens is None:
        return ()
    return model_name_token_edits(contents=contents, tokens=tokens, old=old, new=new)


def model_name_token_edits(
    *, contents: str, tokens: tuple[HeaderToken, ...], old: str, new: str
) -> tuple[TextEdit, ...]:
    """Rename a model in the given header tokens."""

    names: list[HeaderToken] = [
        name for name, _ in cursor_input_tokens(tokens=tokens) if is_value(token=name, value=old)
    ]
    names.extend(
        relationship.target
        for relationship in relationship_tokens(tokens=tokens)
        if relationship.target is not None
        and not relationship.called
        and is_value(token=relationship.target, value=old)
    )
    edits: list[TextEdit] = [
        rename_value_token(contents=contents, token=name, new_value=new, kind=EditKind.HEADER)
        for name in names
    ]
    token: HeaderToken
    for token in tokens:
        if token.kind == HeaderTokenKind.STRING:
            edits.extend(
                text_edit(
                    text=contents,
                    start=token.start + start,
                    end=token.start + end,
                    replacement=new,
                    kind=EditKind.REFERENCE,
                )
                for start, end in embedded_ref_spans(
                    text=contents[token.start : token.end], name=old
                )
            )
    return tuple(edits)


def consumer_column_header_edits(
    *, contents: str, upstream: str, old: str, new: str
) -> tuple[TextEdit, ...]:
    """Rename an upstream column in cursor_inputs values and relationships `field` values."""

    tokens: tuple[HeaderToken, ...] | None = header_tokens(contents=contents)
    if tokens is None:
        return ()
    return column_token_edits(contents=contents, tokens=tokens, upstream=upstream, old=old, new=new)


def column_token_edits(
    *, contents: str, tokens: tuple[HeaderToken, ...], upstream: str, old: str, new: str
) -> tuple[TextEdit, ...]:
    """Rename an upstream column in the given header tokens."""

    values: list[HeaderToken] = []
    name: HeaderToken
    inputs: tuple[HeaderToken, ...]
    for name, inputs in cursor_input_tokens(tokens=tokens):
        if is_value(token=name, value=upstream):
            values.extend(value for value in inputs if is_value(token=value, value=old))
    relationship: RelationshipTokens
    for relationship in relationship_tokens(tokens=tokens):
        if (
            relationship.target is not None
            and relationship.field is not None
            and is_value(token=relationship.target, value=upstream)
            and is_value(token=relationship.field, value=old)
        ):
            values.append(relationship.field)
    return tuple(
        rename_value_token(contents=contents, token=value, new_value=new, kind=EditKind.HEADER)
        for value in values
    )


def quoted_name(name: str) -> str:
    """Return a header value spelling for a name."""

    return name if IDENTIFIER_PATTERN.match(name) else f'"{name}"'


def _column_migration_edit(
    *, contents: str, name: HeaderToken, values: tuple[HeaderToken, ...], old: str
) -> TextEdit:
    declaration: str = f"migrate_from {old}"
    if values and values[0].value == HEADER_OPEN_PAREN:
        opener: HeaderToken = values[0]
        has_metadata: bool = len(values) > PARENTHESIZED_EMPTY_TOKENS
        return text_edit(
            text=contents,
            start=opener.end,
            end=opener.end,
            replacement=f"{declaration}, " if has_metadata else declaration,
            kind=EditKind.MIGRATION,
            before="",
            after=declaration,
        )
    return text_edit(
        text=contents,
        start=name.end,
        end=name.end,
        replacement=f" ({declaration})",
        kind=EditKind.MIGRATION,
        before="",
        after=declaration,
    )


def _relationship(
    *, tokens: tuple[HeaderToken, ...], to_index: int | None, field_index: int | None
) -> RelationshipTokens:
    field: HeaderToken | None = tokens[field_index] if field_index is not None else None
    if to_index is None:
        return RelationshipTokens(target=None, field=field, called=False)
    called: bool = (
        tokens[to_index].value == REF_FUNCTION
        and to_index + 2 < len(tokens)
        and tokens[to_index + 1].value == HEADER_OPEN_PAREN
        and tokens[to_index + 2].kind == HeaderTokenKind.STRING
    )
    return RelationshipTokens(
        target=tokens[to_index + 2] if called else tokens[to_index], field=field, called=called
    )


def _nested_entries(
    *, tokens: tuple[HeaderToken, ...], depth: int
) -> tuple[tuple[HeaderToken, tuple[HeaderToken, ...]], ...]:
    """Split the contents of one bracketed value into (first token, rest) entries."""

    groups: list[list[HeaderToken]] = [[]]
    token: HeaderToken
    for token in tokens:
        if token.depth < depth:
            continue
        if token.depth == depth and _is_separator(token):
            groups.append([])
            continue
        groups[-1].append(token)
    return tuple(
        (group[0], tuple(group[1:])) for group in groups if group and group[0].kind in _VALUE_KINDS
    )


def _is_separator(token: HeaderToken) -> bool:
    return token.kind == HeaderTokenKind.SYMBOL and token.value == HEADER_SEPARATOR


def _token_end(*, contents: str, kind: HeaderTokenKind, value: str, start: int) -> int:
    if kind != HeaderTokenKind.STRING:
        return start + len(value)
    return quoted_value_end(text=contents, start=start)


def _line_indent(*, contents: str, offset: int) -> str:
    line_start: int = contents.rfind("\n", 0, offset) + 1
    prefix: str = contents[line_start:offset]
    return prefix if not prefix.strip() else HEADER_INDENT
