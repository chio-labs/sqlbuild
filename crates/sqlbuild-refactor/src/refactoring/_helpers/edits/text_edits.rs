//! Offsets, positions, and edit application for authored text, as `text_edits.py` does.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::refactoring::_helpers::scanning::chars::{
    count_before, is_identifier_character, rfind, slice, starts_with_ignoring_case,
};
use crate::refactoring::constants::EDIT_ERROR_CODE;
use crate::refactoring::errors::{RefactorError, RefactorErrorKind};
use crate::refactoring::models::{
    EditKind, FileChange, ManualLocation, MigrationDeclaration, RefactorPlan, RefactorRequest,
    TextEdit,
};

/// Edits and findings from one planning step, merged into a plan at the end.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct RefactorParts {
    pub(crate) edits: Vec<(String, TextEdit)>,
    pub(crate) manual: Vec<ManualLocation>,
    pub(crate) blocking: Vec<ManualLocation>,
    pub(crate) migrations: Vec<MigrationDeclaration>,
    pub(crate) cascaded: Vec<String>,
    pub(crate) moves: Vec<(String, String)>,
}

/// The 1-based line and column of an offset.
pub(crate) fn line_column(text: &[char], offset: usize) -> (usize, usize) {
    let line_start = rfind(text, "\n", 0, offset).map_or(0, |index| index + 1);
    (
        count_before(text, '\n', offset) + 1,
        offset - line_start + 1,
    )
}

/// One edit with its position; `before` and `after` default as Python's do.
pub(crate) fn text_edit(
    text: &[char],
    span: (usize, usize),
    replacement: String,
    kind: EditKind,
) -> TextEdit {
    let (start, end) = span;
    let (line, column) = line_column(text, start);
    TextEdit {
        start,
        end,
        before: slice(text, start, end),
        after: python_strip(&replacement).to_owned(),
        replacement,
        kind,
        line,
        column,
    }
}

/// A manual location at an optional offset.
pub(crate) fn manual_at(
    path: &str,
    text: &[char],
    offset: Option<usize>,
    reason: String,
) -> ManualLocation {
    let (line, column) = match offset {
        Some(offset) => {
            let (line, column) = line_column(text, offset);
            (Some(line), Some(column))
        }
        None => (None, None),
    };
    ManualLocation {
        path: path.to_owned(),
        line,
        column,
        reason,
    }
}

/// Apply non-overlapping edits back to front; identical duplicates apply once.
pub(crate) fn apply_text_edits(
    text: &[char],
    edits: &[TextEdit],
) -> Result<Vec<char>, RefactorError> {
    let mut unique: Vec<&TextEdit> = Vec::new();
    for edit in edits {
        let key = (edit.start, edit.end, &edit.replacement);
        match unique
            .iter()
            .position(|item| (item.start, item.end, &item.replacement) == key)
        {
            Some(index) => unique[index] = edit,
            None => unique.push(edit),
        }
    }
    unique.sort_by_key(|edit| std::cmp::Reverse((edit.start, edit.end)));
    let mut result: Vec<char> = text.to_vec();
    let mut previous_start = text.len() + 1;
    for edit in unique {
        if edit.end > previous_start {
            return Err(RefactorError {
                kind: RefactorErrorKind::Edit,
                code: EDIT_ERROR_CODE.to_owned(),
                message: format!("overlapping refactoring edits at offset {}", edit.start),
                help: None,
            });
        }
        let end = edit.end.min(result.len());
        let start = edit.start.min(end);
        result.splice(start..end, edit.replacement.chars());
        previous_start = edit.start;
    }
    Ok(result)
}

/// Concatenate planning parts in order; moves are not merged, as in Python.
pub(crate) fn merge_parts(parts: Vec<RefactorParts>) -> RefactorParts {
    let mut merged = RefactorParts::default();
    for part in parts {
        merged.edits.extend(part.edits);
        merged.manual.extend(part.manual);
        merged.blocking.extend(part.blocking);
        merged.migrations.extend(part.migrations);
        merged.cascaded.extend(part.cascaded);
    }
    merged
}

/// Attach a file path to each edit.
pub(crate) fn path_edits(path: &str, edits: Vec<TextEdit>) -> Vec<(String, TextEdit)> {
    edits
        .into_iter()
        .map(|edit| (path.to_owned(), edit))
        .collect()
}

/// Group edits by file, move files, and order the result by final path.
pub(crate) fn file_changes(
    edits: Vec<(String, TextEdit)>,
    moves: &[(String, String)],
) -> Vec<FileChange> {
    let mut grouped: Vec<(String, Vec<TextEdit>)> = Vec::new();
    for (path, _) in moves {
        if !grouped.iter().any(|(item, _)| item == path) {
            grouped.push((path.clone(), Vec::new()));
        }
    }
    for (path, edit) in edits {
        match grouped.iter_mut().find(|(item, _)| *item == path) {
            Some((_, items)) => items.push(edit),
            None => grouped.push((path, vec![edit])),
        }
    }
    let mut changes: Vec<FileChange> = grouped
        .into_iter()
        .map(|(path, items)| FileChange {
            path: moved_path(moves, &path),
            original_path: path,
            edits: items,
        })
        .collect();
    changes.sort_by(|left, right| left.path.cmp(&right.path));
    changes
}

/// `moves.get(path, path)` over moves where a later entry for a path wins, as in a dict.
fn moved_path(moves: &[(String, String)], path: &str) -> String {
    moves
        .iter()
        .rev()
        .find(|(source, _)| source == path)
        .map_or_else(|| path.to_owned(), |(_, destination)| destination.clone())
}

/// Assemble a plan from merged parts; help applies only when manual locations exist.
pub(crate) fn build_plan(
    request: RefactorRequest,
    parts: RefactorParts,
    moves: &[(String, String)],
    outcome: (Vec<(String, String, String)>, Option<&str>),
) -> RefactorPlan {
    let (renamed_columns, help) = outcome;
    let help = (!parts.manual.is_empty())
        .then_some(help)
        .flatten()
        .map(str::to_owned);
    RefactorPlan {
        request,
        changes: file_changes(parts.edits, moves),
        manual: parts.manual,
        blocking: parts.blocking,
        migrations: parts.migrations,
        renamed_columns,
        help,
    }
}

/// Unquoted code identifiers matching `names`, as `identifier_sites` finds them.
pub(crate) fn identifier_sites(text: &[char], names: &[String]) -> Vec<(usize, usize, String)> {
    if names.is_empty() {
        return Vec::new();
    }
    let mut lowered: Vec<(String, String)> = Vec::new();
    for name in names {
        let key = name.to_lowercase();
        match lowered.iter_mut().find(|(item, _)| *item == key) {
            Some(entry) => entry.1 = name.clone(),
            None => lowered.push((key, name.clone())),
        }
    }
    let mut ordered: Vec<Vec<char>> = lowered
        .iter()
        .map(|(key, _)| key.chars().collect())
        .collect();
    ordered.sort_by(|left, right| right.len().cmp(&left.len()).then_with(|| left.cmp(right)));
    let mut sites: Vec<(usize, usize, String)> = Vec::new();
    let mut index = 0;
    while index < text.len() {
        if let Some(end) = non_code_end(text, index) {
            index = end;
            continue;
        }
        let preceded = index > 0 && is_identifier_character(text[index - 1]);
        let found = (!preceded)
            .then(|| {
                ordered.iter().find(|name| {
                    starts_with_ignoring_case(text, index, name)
                        && !text
                            .get(index + name.len())
                            .is_some_and(|next| is_identifier_character(*next))
                })
            })
            .flatten();
        match found {
            Some(name) => {
                let end = index + name.len();
                let token: String = slice(text, index, end).to_lowercase();
                let canonical = lowered
                    .iter()
                    .find(|(key, _)| *key == token)
                    .map_or_else(|| token.clone(), |(_, name)| name.clone());
                sites.push((index, end, canonical));
                index = end;
            }
            None => index += 1,
        }
    }
    sites
}

/// The end of `NON_CODE_PATTERN` matched at `index`: a comment or a quoted string.
fn non_code_end(text: &[char], index: usize) -> Option<usize> {
    let at = |offset: usize| text.get(index + offset).copied();
    match (at(0), at(1)) {
        (Some('-'), Some('-')) => Some(
            (index + 2..text.len())
                .find(|position| text[*position] == '\n')
                .map_or(text.len(), |position| position + 1),
        ),
        (Some('/'), Some('*')) => Some(
            (index + 2..text.len().saturating_sub(1))
                .find(|position| text[*position] == '*' && text[*position + 1] == '/')
                .map_or(text.len(), |position| position + 2),
        ),
        (Some(quote @ ('\'' | '"')), _) => {
            let mut position = index + 1;
            while position < text.len() {
                if text[position] == quote {
                    if text.get(position + 1) == Some(&quote) {
                        position += 2;
                        continue;
                    }
                    return Some(position + 1);
                }
                position += 1;
            }
            Some(text.len())
        }
        _ => None,
    }
}

/// Offsets of a case-insensitive whole identifier word anywhere in `text`.
pub(crate) fn whole_word_offsets(text: &[char], word: &str) -> Vec<usize> {
    let word: Vec<char> = word.chars().collect();
    let mut offsets: Vec<usize> = Vec::new();
    let mut index = 0;
    while index + word.len() <= text.len() {
        let preceded = index > 0 && is_identifier_character(text[index - 1]);
        let followed = text
            .get(index + word.len())
            .is_some_and(|next| is_identifier_character(*next));
        if !preceded && !followed && starts_with_ignoring_case(text, index, &word) {
            offsets.push(index);
            index += word.len().max(1);
            continue;
        }
        index += 1;
    }
    offsets
}
