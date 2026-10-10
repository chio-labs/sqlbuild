//! Token-exact MODEL and SCHEMA header edits for renamed models and columns, as
//! `header_edits.py` and `schema_edits.py` make them.

use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::is_python_word::is_python_word;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::main::model_header_matching::match_batch;
use sqlbuild_sqltext::compiler::main::model_header_tokenizing::tokenize_one;
use sqlbuild_sqltext::compiler::main::statement_header_matching::match_statement_header;

use crate::refactoring::_helpers::chars::{find, rfind, slice, starts_with};
use crate::refactoring::_helpers::sql_sites::embedded_ref_spans;
use crate::refactoring::_helpers::text_edits::{text_edit, whole_word_offsets};
use crate::refactoring::constants::{
    COLUMN_VALUED_CONFIG_KEYS, COLUMNS_KEY, CURSOR_INPUTS_KEY, HEADER_CLOSERS,
    HEADER_DESCRIPTION_KEY, HEADER_INDENT, HEADER_KEY_AND_VALUE_TOKENS, HEADER_OPEN_PAREN,
    HEADER_OPENERS, HEADER_SEPARATOR, MIGRATE_FROM_KEY, PARENTHESIZED_EMPTY_TOKENS, REF_FUNCTION,
    RELATIONSHIPS_AUDIT, RELATIONSHIPS_FIELD_KEY, RELATIONSHIPS_TO_KEY, SCHEMA_KEYWORD,
};
use crate::refactoring::models::{EditKind, RefactorError, TextEdit};

const END_TOKEN: u8 = 0;
const WORD_TOKEN: u8 = 1;
const STRING_TOKEN: u8 = 2;
const SYMBOL_TOKEN: u8 = 3;

/// MODEL header token kinds.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum HeaderTokenKind {
    Word,
    String,
    Symbol,
}

/// One header token in file offsets, with its nesting depth.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct HeaderToken {
    pub(crate) kind: HeaderTokenKind,
    pub(crate) value: String,
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) depth: i64,
}

type NestedEntry<'a> = (&'a HeaderToken, Vec<&'a HeaderToken>);

/// The relationships audit target and field value tokens.
struct RelationshipTokens<'a> {
    target: Option<&'a HeaderToken>,
    field: Option<&'a HeaderToken>,
    called: bool,
}

fn is_value_kind(kind: HeaderTokenKind) -> bool {
    matches!(kind, HeaderTokenKind::Word | HeaderTokenKind::String)
}

/// The code-point span of the MODEL header body, as `get_model_header_spans(...).body`.
pub(crate) fn model_header_body_span(contents: &str) -> Option<(usize, usize)> {
    match_batch(&[contents.to_owned()])
        .into_iter()
        .next()
        .flatten()
        .map(|(start, end, _)| (start, end))
}

/// Tokenize the MODEL header body in file offsets, or `None` without a header.
pub(crate) fn header_tokens(
    contents: &str,
    text: &[char],
) -> Result<Option<Vec<HeaderToken>>, RefactorError> {
    match model_header_body_span(contents) {
        Some(span) => span_tokens(text, span).map(Some),
        None => Ok(None),
    }
}

/// Tokenize one declaration header body in file offsets.
pub(crate) fn span_tokens(
    text: &[char],
    span: (usize, usize),
) -> Result<Vec<HeaderToken>, RefactorError> {
    let body = slice(text, span.0, span.1);
    let raw = tokenize_one(&body).map_err(RefactorError::value)?;
    let mut tokens: Vec<HeaderToken> = Vec::new();
    let mut depth: i64 = 0;
    for (raw_kind, value, position) in raw {
        let kind = match raw_kind {
            END_TOKEN => continue,
            WORD_TOKEN => HeaderTokenKind::Word,
            STRING_TOKEN => HeaderTokenKind::String,
            SYMBOL_TOKEN => HeaderTokenKind::Symbol,
            _ => continue,
        };
        let start = span.0 + position;
        let end = if kind == HeaderTokenKind::String {
            quoted_value_end(text, start)
        } else {
            start + value.chars().count()
        };
        if kind == HeaderTokenKind::Symbol && HEADER_CLOSERS.contains(&value.as_str()) {
            depth -= 1;
        }
        let opens = kind == HeaderTokenKind::Symbol && HEADER_OPENERS.contains(&value.as_str());
        tokens.push(HeaderToken {
            kind,
            value,
            start,
            end,
            depth,
        });
        if opens {
            depth += 1;
        }
    }
    Ok(tokens)
}

/// The offset just past the quoted value that opens at `start` (`quoted_value_end`).
fn quoted_value_end(text: &[char], start: usize) -> usize {
    let Some(&quote) = text.get(start) else {
        return text.len();
    };
    let mut index = start + 1;
    while index < text.len() {
        if text[index] == '\\' && index + 1 < text.len() {
            index += 2;
            continue;
        }
        if text[index] == quote {
            return index + 1;
        }
        index += 1;
    }
    text.len()
}

fn is_separator(token: &HeaderToken) -> bool {
    token.kind == HeaderTokenKind::Symbol && token.value == HEADER_SEPARATOR
}

/// Split the contents of one bracketed value into `(first token, rest)` entries.
fn nested_entries<'a>(tokens: &[&'a HeaderToken], depth: i64) -> Vec<NestedEntry<'a>> {
    let mut groups: Vec<Vec<&'a HeaderToken>> = vec![Vec::new()];
    for token in tokens {
        if token.depth < depth {
            continue;
        }
        if token.depth == depth && is_separator(token) {
            groups.push(Vec::new());
            continue;
        }
        if let Some(group) = groups.last_mut() {
            group.push(token);
        }
    }
    groups
        .into_iter()
        .filter(|group| group.first().is_some_and(|first| is_value_kind(first.kind)))
        .map(|group| (group[0], group[1..].to_vec()))
        .collect()
}

/// Top-level `key value` entries keyed by their first word.
fn header_entries(tokens: &[HeaderToken]) -> Vec<(String, Vec<&HeaderToken>)> {
    let all: Vec<&HeaderToken> = tokens.iter().collect();
    nested_entries(&all, 0)
        .into_iter()
        .filter(|(first, _)| first.kind == HeaderTokenKind::Word)
        .map(|(first, rest)| {
            let mut entry = vec![first];
            entry.extend(rest);
            (first.value.clone(), entry)
        })
        .collect()
}

/// Whether a word or string token spells a name, ignoring case.
pub(crate) fn is_value(token: &HeaderToken, value: &str) -> bool {
    is_value_kind(token.kind) && token.value.to_lowercase() == value.to_lowercase()
}

/// Replace one word or string value, keeping string quoting.
fn rename_value_token(
    text: &[char],
    token: &HeaderToken,
    new_value: &str,
    kind: EditKind,
) -> TextEdit {
    let replacement = if token.kind == HeaderTokenKind::Word {
        new_value.to_owned()
    } else {
        let quote = text[token.start];
        format!("{quote}{new_value}{quote}")
    };
    text_edit(
        text,
        (token.start, token.end),
        replacement,
        kind,
        (None, None),
    )
}

/// `(input name token, value tokens)` for every `cursor_inputs` entry.
fn cursor_input_tokens(tokens: &[HeaderToken]) -> Vec<NestedEntry<'_>> {
    header_entries(tokens)
        .into_iter()
        .find(|(key, _)| key == CURSOR_INPUTS_KEY)
        .map(|(_, entry)| nested_entries(&entry[1..], 1))
        .unwrap_or_default()
}

/// The target and field value tokens of every relationships audit.
fn relationship_tokens(tokens: &[HeaderToken]) -> Vec<RelationshipTokens<'_>> {
    let mut found: Vec<RelationshipTokens<'_>> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if !(token.kind == HeaderTokenKind::Word
            && token.value == RELATIONSHIPS_AUDIT
            && index + 1 < tokens.len()
            && tokens[index + 1].value == HEADER_OPEN_PAREN)
        {
            continue;
        }
        let depth = tokens[index + 1].depth + 1;
        let mut to_index: Option<usize> = None;
        let mut field_index: Option<usize> = None;
        let mut cursor = index + 2;
        while cursor < tokens.len() && tokens[cursor].depth >= depth {
            let candidate = &tokens[cursor];
            if candidate.depth == depth
                && candidate.kind == HeaderTokenKind::Word
                && cursor + 1 < tokens.len()
            {
                if candidate.value == RELATIONSHIPS_TO_KEY {
                    to_index = Some(cursor + 1);
                } else if candidate.value == RELATIONSHIPS_FIELD_KEY {
                    field_index = Some(cursor + 1);
                }
            }
            cursor += 1;
        }
        found.push(relationship(tokens, to_index, field_index));
    }
    found
}

fn relationship(
    tokens: &[HeaderToken],
    to_index: Option<usize>,
    field_index: Option<usize>,
) -> RelationshipTokens<'_> {
    let field = field_index.map(|index| &tokens[index]);
    let Some(to_index) = to_index else {
        return RelationshipTokens {
            target: None,
            field,
            called: false,
        };
    };
    let called = tokens[to_index].value == REF_FUNCTION
        && to_index + 2 < tokens.len()
        && tokens[to_index + 1].value == HEADER_OPEN_PAREN
        && tokens[to_index + 2].kind == HeaderTokenKind::String;
    RelationshipTokens {
        target: Some(if called {
            &tokens[to_index + 2]
        } else {
            &tokens[to_index]
        }),
        field,
        called,
    }
}

/// Rename a column in column-valued config such as `cursor` or `unique_key`.
pub(crate) fn column_config_edits(
    text: &[char],
    tokens: &[HeaderToken],
    old: &str,
    new: &str,
) -> Vec<TextEdit> {
    let mut edits: Vec<TextEdit> = Vec::new();
    for (key, entry) in header_entries(tokens) {
        if !COLUMN_VALUED_CONFIG_KEYS.contains(&key.as_str()) {
            continue;
        }
        for token in &entry[1..] {
            if is_value(token, old) {
                edits.push(rename_value_token(text, token, new, EditKind::Header));
            }
        }
    }
    edits
}

/// Rename a `columns` entry and add `migrate_from` if needed; `None` without an entry.
pub(crate) fn column_entry_edits(
    text: &[char],
    tokens: &[HeaderToken],
    names: (&str, &str),
    migrate: bool,
) -> Option<Vec<TextEdit>> {
    let (old, new) = names;
    for (key, entry) in header_entries(tokens) {
        if key != COLUMNS_KEY {
            continue;
        }
        for (name_token, values) in nested_entries(&entry[1..], 1) {
            if !is_value(name_token, old) {
                continue;
            }
            let mut edits = vec![rename_value_token(text, name_token, new, EditKind::Header)];
            if migrate {
                edits.push(column_migration_edit(text, name_token, &values, old));
            }
            return Some(edits);
        }
    }
    None
}

/// Declare `new (migrate_from old)` in the columns block, creating it when absent.
pub(crate) fn add_column_entry_edit(
    contents: &str,
    text: &[char],
    tokens: &[HeaderToken],
    names: (&str, &str),
) -> Option<TextEdit> {
    let (old, new) = names;
    let declaration = format!("{new} ({MIGRATE_FROM_KEY} {old})");
    for (key, entry) in header_entries(tokens) {
        if key != COLUMNS_KEY || entry.len() < HEADER_KEY_AND_VALUE_TOKENS {
            continue;
        }
        let opener = entry[1];
        let indentation = line_indent(text, entry[0].start);
        return Some(text_edit(
            text,
            (opener.end, opener.end),
            format!("\n{indentation}{HEADER_INDENT}{declaration},"),
            EditKind::Migration,
            (Some(String::new()), Some(declaration)),
        ));
    }
    insert_header_entry_edit(
        contents,
        text,
        &format!("{COLUMNS_KEY} ({declaration})"),
        &declaration,
    )
}

/// Insert one top-level entry as the first MODEL header line.
pub(crate) fn insert_header_entry_edit(
    contents: &str,
    text: &[char],
    entry: &str,
    display: &str,
) -> Option<TextEdit> {
    let (start, end) = model_header_body_span(contents)?;
    let body: Vec<char> = text[start..end].to_vec();
    let replacement = if starts_with(&body, 0, "\n") {
        let first_line: Vec<char> = match find(&body, "\n", 1) {
            Some(line_end) => body[1..line_end].to_vec(),
            None => body[1..].to_vec(),
        };
        let indent_length = first_line
            .iter()
            .take_while(|character| is_python_space(**character))
            .count();
        let indentation: String = if indent_length == 0 {
            HEADER_INDENT.to_owned()
        } else {
            first_line[..indent_length].iter().collect()
        };
        format!("\n{indentation}{entry},")
    } else if body.iter().any(|character| !is_python_space(*character)) {
        format!("{entry}, ")
    } else {
        format!("\n{HEADER_INDENT}{entry},\n")
    };
    Some(text_edit(
        text,
        (start, start),
        replacement,
        EditKind::Migration,
        (Some(String::new()), Some(display.to_owned())),
    ))
}

/// Header offsets that still mention a word outside descriptions.
pub(crate) fn unhandled_word_offsets(
    text: &[char],
    tokens: &[HeaderToken],
    word: &str,
    handled: &[usize],
) -> Vec<usize> {
    let mut offsets: Vec<usize> = Vec::new();
    let mut previous: Option<&HeaderToken> = None;
    for token in tokens {
        let described = previous.is_some_and(|item| item.value == HEADER_DESCRIPTION_KEY);
        previous = Some(token);
        if token.kind == HeaderTokenKind::Symbol || described || handled.contains(&token.start) {
            continue;
        }
        let token_text: Vec<char> = text[token.start..token.end.min(text.len())].to_vec();
        offsets.extend(
            whole_word_offsets(&token_text, word)
                .into_iter()
                .map(|offset| token.start + offset),
        );
    }
    offsets
}

/// Rename a model in `cursor_inputs` keys, bare relationships targets, and quoted SQL.
pub(crate) fn model_name_header_edits(
    contents: &str,
    text: &[char],
    old: &str,
    new: &str,
) -> Result<Vec<TextEdit>, RefactorError> {
    Ok(match header_tokens(contents, text)? {
        Some(tokens) => model_name_token_edits(text, &tokens, old, new),
        None => Vec::new(),
    })
}

/// Rename a model in the given header tokens.
fn model_name_token_edits(
    text: &[char],
    tokens: &[HeaderToken],
    old: &str,
    new: &str,
) -> Vec<TextEdit> {
    let mut names: Vec<&HeaderToken> = cursor_input_tokens(tokens)
        .into_iter()
        .map(|(name, _)| name)
        .filter(|name| is_value(name, old))
        .collect();
    names.extend(
        relationship_tokens(tokens)
            .into_iter()
            .filter(|relationship| !relationship.called)
            .filter_map(|relationship| relationship.target)
            .filter(|target| is_value(target, old)),
    );
    let mut edits: Vec<TextEdit> = names
        .into_iter()
        .map(|name| rename_value_token(text, name, new, EditKind::Header))
        .collect();
    for token in tokens {
        if token.kind != HeaderTokenKind::String {
            continue;
        }
        let raw: Vec<char> = text[token.start..token.end.min(text.len())].to_vec();
        edits.extend(
            embedded_ref_spans(&raw, old)
                .into_iter()
                .map(|(start, end)| {
                    text_edit(
                        text,
                        (token.start + start, token.start + end),
                        new.to_owned(),
                        EditKind::Reference,
                        (None, None),
                    )
                }),
        );
    }
    edits
}

/// Rename an upstream column in `cursor_inputs` values and relationships `field` values.
pub(crate) fn consumer_column_header_edits(
    contents: &str,
    text: &[char],
    upstream: &str,
    names: (&str, &str),
) -> Result<Vec<TextEdit>, RefactorError> {
    Ok(match header_tokens(contents, text)? {
        Some(tokens) => column_token_edits(text, &tokens, upstream, names),
        None => Vec::new(),
    })
}

/// Rename an upstream column in the given header tokens.
fn column_token_edits(
    text: &[char],
    tokens: &[HeaderToken],
    upstream: &str,
    names: (&str, &str),
) -> Vec<TextEdit> {
    let (old, new) = names;
    let mut values: Vec<&HeaderToken> = Vec::new();
    for (name, inputs) in cursor_input_tokens(tokens) {
        if is_value(name, upstream) {
            values.extend(inputs.into_iter().filter(|value| is_value(value, old)));
        }
    }
    for relationship in relationship_tokens(tokens) {
        if let (Some(target), Some(field)) = (relationship.target, relationship.field)
            && is_value(target, upstream)
            && is_value(field, old)
        {
            values.push(field);
        }
    }
    values
        .into_iter()
        .map(|value| rename_value_token(text, value, new, EditKind::Header))
        .collect()
}

fn column_migration_edit(
    text: &[char],
    name: &HeaderToken,
    values: &[&HeaderToken],
    old: &str,
) -> TextEdit {
    let declaration = format!("{MIGRATE_FROM_KEY} {old}");
    if let Some(opener) = values
        .first()
        .filter(|first| first.value == HEADER_OPEN_PAREN)
    {
        let has_metadata = values.len() > PARENTHESIZED_EMPTY_TOKENS;
        let replacement = if has_metadata {
            format!("{declaration}, ")
        } else {
            declaration.clone()
        };
        return text_edit(
            text,
            (opener.end, opener.end),
            replacement,
            EditKind::Migration,
            (Some(String::new()), Some(declaration)),
        );
    }
    text_edit(
        text,
        (name.end, name.end),
        format!(" ({declaration})"),
        EditKind::Migration,
        (Some(String::new()), Some(declaration)),
    )
}

fn line_indent(text: &[char], offset: usize) -> String {
    let line_start = rfind(text, "\n", 0, offset).map_or(0, |index| index + 1);
    let prefix: Vec<char> = text[line_start..offset].to_vec();
    if prefix.iter().all(|character| is_python_space(*character)) {
        prefix.into_iter().collect()
    } else {
        HEADER_INDENT.to_owned()
    }
}

/// Code-point spans of every `SCHEMA (...)` header body, as `SCHEMA_STATEMENT_PATTERN.finditer`.
fn schema_header_spans(contents: &str, text: &[char], python: PythonText) -> Vec<(usize, usize)> {
    let mut byte_offsets: Vec<usize> = contents.char_indices().map(|(offset, _)| offset).collect();
    byte_offsets.push(contents.len());
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut index = 0;
    while index < text.len() {
        let bounded = index == 0 || !is_python_word(python, text[index - 1]);
        if bounded
            && starts_with(text, index, SCHEMA_KEYWORD)
            && let Some((start, end, _)) =
                match_statement_header(contents, byte_offsets[index], SCHEMA_KEYWORD)
        {
            let start = byte_to_char(&byte_offsets, start);
            let end = byte_to_char(&byte_offsets, end);
            spans.push((start, end));
            index = statement_end(text, end);
            continue;
        }
        index += 1;
    }
    spans
}

/// The end of `\)\s*;` after a header body ending at `end`.
fn statement_end(text: &[char], end: usize) -> usize {
    let mut index = end + 1;
    while text.get(index).copied().is_some_and(is_python_space) {
        index += 1;
    }
    index + 1
}

fn byte_to_char(byte_offsets: &[usize], byte: usize) -> usize {
    byte_offsets.partition_point(|offset| *offset < byte)
}

/// Rename a model in every SCHEMA header of a declaration file.
pub(crate) fn schema_model_name_edits(
    contents: &str,
    text: &[char],
    names: (&str, &str),
    python: PythonText,
) -> Result<Vec<TextEdit>, RefactorError> {
    let mut edits: Vec<TextEdit> = Vec::new();
    for span in schema_header_spans(contents, text, python) {
        edits.extend(model_name_token_edits(
            text,
            &span_tokens(text, span)?,
            names.0,
            names.1,
        ));
    }
    Ok(edits)
}

/// Rename relationships `field` values pointing at a renamed column of a model.
pub(crate) fn schema_column_edits(
    contents: &str,
    text: &[char],
    upstream: &str,
    names: (&str, &str),
    python: PythonText,
) -> Result<Vec<TextEdit>, RefactorError> {
    let mut edits: Vec<TextEdit> = Vec::new();
    for span in schema_header_spans(contents, text, python) {
        edits.extend(column_token_edits(
            text,
            &span_tokens(text, span)?,
            upstream,
            names,
        ));
    }
    Ok(edits)
}
