//! Contract adoption's MODEL header edit, as Python's `edit_model` plans it.

use sqlbuild_model_config::name_patterns::main::compile_name_pattern::compile_name_pattern;
use sqlbuild_sqltext::compiler::models::{HeaderColumnSpan, HeaderColumns};

use crate::refactoring::_helpers::contracts::model_types::{declared_type_span, render_model_type};
use crate::refactoring::_helpers::edits::text_edits::{apply_text_edits, text_edit};
use crate::refactoring::_helpers::scanning::chars::{find, slice};
use crate::refactoring::constants::{
    CONTRACT_DEFAULT_INDENT, CONTRACT_HEADER_WHITESPACE, CONTRACT_OVERLAP_MESSAGE,
    EXTERNAL_SCHEMA_CONFLICT, INVALID_NAME_PATTERN_PREFIX, SHARED_SCHEMA_CONFLICT,
};
use crate::refactoring::errors::{RefactorError, RefactorErrorKind};
use crate::refactoring::models::{
    ContractEdit, ContractModelColumn, ContractModelRequest, EditKind, TextEdit,
};
use crate::refactoring::types::PhysicalColumn;

/// A Python dict built by assignment: each key keeps its first position and its last value.
pub(crate) fn python_dict<'a, T>(
    items: impl Iterator<Item = (String, &'a T)>,
) -> Vec<(String, &'a T)> {
    let mut entries: Vec<(String, &'a T)> = Vec::new();
    for (key, value) in items {
        match entries.iter_mut().find(|(existing, _)| *existing == key) {
            Some(entry) => entry.1 = value,
            None => entries.push((key, value)),
        }
    }
    entries
}

/// The conflict `edit_model` reports before reading the header, if any.
pub(crate) fn ownership_conflict(request: &ContractModelRequest) -> Option<ContractEdit> {
    if request.shared_schema {
        return Some(ContractEdit::Conflict(SHARED_SCHEMA_CONFLICT.to_owned()));
    }
    request
        .columns
        .iter()
        .any(|column| {
            column
                .location_path
                .as_ref()
                .is_some_and(|path| *path != request.relative_path)
        })
        .then(|| ContractEdit::Conflict(EXTERNAL_SCHEMA_CONFLICT.to_owned()))
}

/// Whether any family accepts `name`; every pattern is compiled, as Python's tuple filter does.
fn family_member(patterns: &[Option<String>], name: &str) -> Result<bool, RefactorError> {
    let mut member = false;
    for pattern in patterns {
        member |= match pattern {
            None => true,
            Some(pattern) => compile_name_pattern(pattern)
                .map_err(|reason| {
                    RefactorError::value(format!("{INVALID_NAME_PATTERN_PREFIX}{reason}"))
                })?
                .matches(name),
        };
    }
    Ok(member)
}

/// Physical columns without the runtime members of declared dynamic families.
pub(crate) fn fixed_physical_columns(
    request: &ContractModelRequest,
) -> Result<Vec<PhysicalColumn>, RefactorError> {
    if request.dynamic_patterns.is_empty() {
        return Ok(request.physical_columns.clone());
    }
    let fixed: Vec<String> = request
        .columns
        .iter()
        .map(|column| str::to_lowercase(&column.name))
        .collect();
    let mut kept: Vec<PhysicalColumn> = Vec::new();
    for column in &request.physical_columns {
        if fixed.contains(&str::to_lowercase(&column.0))
            || !family_member(&request.dynamic_patterns, &column.0)?
        {
            kept.push(column.clone());
        }
    }
    Ok(kept)
}

/// Python's `_render_model_columns` inserted after the header body: `\n  columns (...)`.
pub(crate) fn columns_block(columns: &[PhysicalColumn]) -> String {
    let body: String = columns
        .iter()
        .map(|(name, column_type)| {
            format!("\n    {name} (type {})", render_model_type(column_type))
        })
        .collect();
    format!("\n  columns ({body}\n  )")
}

/// Python's `_column_indentation`: the indent of the line after the columns body opens.
fn column_indentation(text: &[char], body_start: usize) -> String {
    let Some(next_line) = find(text, "\n", body_start) else {
        return CONTRACT_DEFAULT_INDENT.to_owned();
    };
    let indentation: String = text[next_line + 1..]
        .iter()
        .take_while(|character| CONTRACT_HEADER_WHITESPACE.contains(character))
        .collect();
    if indentation.is_empty() {
        CONTRACT_DEFAULT_INDENT.to_owned()
    } else {
        indentation
    }
}

fn edit(text: &[char], span: (usize, usize), replacement: String) -> TextEdit {
    text_edit(text, span, replacement, EditKind::Column)
}

/// The edit one declared column needs, `Ok(None)` for none, or the conflict that stops all edits.
fn declared_column_edit(
    text: &[char],
    column: &ContractModelColumn,
    (span, physical_type): (&HeaderColumnSpan, Option<&str>),
    overwrite: bool,
) -> Result<Option<TextEdit>, String> {
    let Some(physical_type) = physical_type else {
        return Ok(overwrite.then(|| edit(text, (span.entry_start, span.entry_end), String::new())));
    };
    match &column.declared_type {
        None => {
            let metadata = slice(text, span.metadata_start, span.metadata_end);
            let separator = if str::trim(&metadata).is_empty() {
                ""
            } else {
                ", "
            };
            Ok(Some(edit(
                text,
                (span.metadata_start, span.metadata_start),
                format!("type {}{separator}", render_model_type(physical_type)),
            )))
        }
        Some(declared)
            if overwrite && str::to_lowercase(declared) != str::to_lowercase(physical_type) =>
        {
            declared_type_span(text, (span.metadata_start, span.metadata_end), declared)
                .map(|replacement| Some(edit(text, replacement, render_model_type(physical_type))))
                .ok_or_else(|| {
                    format!(
                        "column '{}' type span could not be edited safely",
                        column.name
                    )
                })
        }
        Some(_) => Ok(None),
    }
}

/// The edits of every declared column, in Python's dict order, or the first conflict.
fn declared_edits(
    text: &[char],
    request: &ContractModelRequest,
    columns: &HeaderColumns,
    physical: &[PhysicalColumn],
) -> Result<Vec<TextEdit>, String> {
    let declared = python_dict(
        request
            .columns
            .iter()
            .map(|column| (str::to_lowercase(&column.name), column)),
    );
    let physical_by_name = python_dict(
        physical
            .iter()
            .map(|column| (str::to_lowercase(&column.0), column)),
    );
    let mut edits: Vec<TextEdit> = Vec::new();
    for (name, column) in &declared {
        let Some((_, span)) = columns
            .entries
            .iter()
            .rev()
            .find(|(entry, _)| *entry == column.name)
        else {
            return Err(format!(
                "column '{}' has no unambiguous authored span",
                column.name
            ));
        };
        let physical_type = physical_by_name
            .iter()
            .find(|(key, _)| key == name)
            .map(|(_, (_, column_type))| column_type.as_str());
        edits.extend(declared_column_edit(
            text,
            column,
            (span, physical_type),
            request.overwrite,
        )?);
    }
    Ok(edits)
}

/// The physical columns no declared column names, rendered as new `columns` entries.
fn additions(
    text: &[char],
    columns: &HeaderColumns,
    request: &ContractModelRequest,
    physical: &[PhysicalColumn],
) -> String {
    let declared: Vec<String> = request
        .columns
        .iter()
        .map(|column| str::to_lowercase(&column.name))
        .collect();
    let indentation = column_indentation(text, columns.body_start);
    let mut rendered = String::new();
    for (name, column_type) in physical {
        if !declared.contains(&str::to_lowercase(name)) {
            rendered.push_str(&format!(
                "\n{indentation}{name} (type {})",
                render_model_type(column_type)
            ));
        }
    }
    rendered
}

/// Python's `edit_model` once the header declares `columns (...)`.
pub(crate) fn columns_edit(
    text: &[char],
    request: &ContractModelRequest,
    columns: &HeaderColumns,
    physical: &[PhysicalColumn],
) -> Result<ContractEdit, RefactorError> {
    let mut edits = match declared_edits(text, request, columns, physical) {
        Ok(edits) => edits,
        Err(conflict) => return Ok(ContractEdit::Conflict(conflict)),
    };
    let added = additions(text, columns, request, physical);
    if !added.is_empty() {
        edits.push(edit(
            text,
            (columns.body_end, columns.body_end),
            format!("{added}\n  "),
        ));
    }
    edits.sort_by(|left, right| {
        (right.start, right.end, &right.replacement).cmp(&(left.start, left.end, &left.replacement))
    });
    match apply_text_edits(text, &edits) {
        Ok(edited) => Ok(ContractEdit::Edited(edited.into_iter().collect())),
        Err(error) if error.kind == RefactorErrorKind::Edit => Err(RefactorError {
            message: CONTRACT_OVERLAP_MESSAGE.to_owned(),
            ..error
        }),
        Err(error) => Err(error),
    }
}
