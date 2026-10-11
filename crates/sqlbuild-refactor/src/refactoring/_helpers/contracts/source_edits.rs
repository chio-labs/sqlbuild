//! Contract adoption's YAML source declaration edit, as Python's `edit_source` plans it.

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_core::text::main::python_splitlines::python_splitlines;

use crate::refactoring::_helpers::contracts::model_edits::python_dict;
use crate::refactoring::_helpers::contracts::yaml_lines::{
    column_lines, comment, indent, is_content, key, list_name, sequence_indent, yaml_string,
};
use crate::refactoring::constants::{
    CONTRACT_GENERATED_MARKER, CONTRACT_GENERATED_MARKER_LINES, CONTRACT_TYPE_KEY,
    CONTRACT_YAML_COLUMNS_KEY,
};
use crate::refactoring::models::ContractSourceRequest;
use crate::refactoring::types::LineEdit;

/// Whether the first lines of the discovered file mark it as generated.
pub(crate) fn is_generated(contents: &str) -> bool {
    let head: Vec<&str> = python_splitlines(contents)
        .into_iter()
        .take(CONTRACT_GENERATED_MARKER_LINES)
        .collect();
    python_casefold(active_python_text(), &head.join("\n")).contains(CONTRACT_GENERATED_MARKER)
}

/// The `columns:` key directly under the source block `(start, end, indent)`.
pub(crate) fn columns_key(
    lines: &[&str],
    (start, end, source_indent): (usize, usize, usize),
) -> Option<usize> {
    (start + 1..end).find(|index| {
        key(lines[*index]) == Some(CONTRACT_YAML_COLUMNS_KEY)
            && indent(lines[*index]) == source_indent + 2
    })
}

/// A new `columns:` key holding every physical column, inserted at the source block's end.
pub(crate) fn columns_insertion(
    request: &ContractSourceRequest,
    source_indent: usize,
) -> Vec<String> {
    let mut insertion = vec![format!("{}columns:\n", " ".repeat(source_indent + 2))];
    for (name, column_type) in &request.physical_columns {
        insertion.extend(column_lines(name, column_type, source_indent + 4));
    }
    insertion
}

/// The end of the `columns:` block: the first content line that leaves it.
fn columns_end(
    lines: &[&str],
    columns_index: usize,
    column_indent: usize,
    source_end: usize,
) -> usize {
    let columns_indent = indent(lines[columns_index]);
    (columns_index + 1..source_end)
        .find(|index| {
            let line = lines[*index];
            let line_indent = indent(line);
            is_content(line)
                && (line_indent < columns_indent
                    || (line_indent == columns_indent
                        && !(column_indent == columns_indent && list_name(line).is_some())))
        })
        .unwrap_or(source_end)
}

/// Each casefolded column name's `(start, end)` line block, in Python's dict order.
fn column_blocks(
    lines: &[&str],
    (start, end): (usize, usize),
    column_indent: usize,
) -> Vec<(String, (usize, usize))> {
    let python = active_python_text();
    let mut found: Vec<(String, (usize, usize))> = Vec::new();
    let mut index = start;
    while index < end {
        match list_name(lines[index]) {
            Some(name) if indent(lines[index]) == column_indent => {
                let block_end = (index + 1..end)
                    .find(|line| {
                        indent(lines[*line]) <= column_indent && list_name(lines[*line]).is_some()
                    })
                    .unwrap_or(end);
                found.push((python_casefold(python, name), (index, block_end)));
                index = block_end;
            }
            _ => index += 1,
        }
    }
    python_dict(found.iter().map(|(name, block)| (name.clone(), block)))
        .into_iter()
        .map(|(name, block)| (name, *block))
        .collect()
}

/// The type-line edit of one declared column whose physical column exists.
fn type_edit(
    lines: &[&str],
    block: (usize, usize),
    (declared_type, physical_type): (Option<&str>, &str),
    (column_indent, overwrite): (usize, bool),
) -> Option<LineEdit> {
    let python = active_python_text();
    let typed = format!(
        "{}type: {}",
        " ".repeat(column_indent + 2),
        yaml_string(physical_type)
    );
    match (block.0 + 1..block.1).find(|line| key(lines[*line]) == Some(CONTRACT_TYPE_KEY)) {
        None => Some((block.0 + 1, block.0 + 1, vec![format!("{typed}\n")])),
        Some(type_line)
            if overwrite
                && declared_type.is_some_and(|declared| {
                    python_casefold(python, declared) != python_casefold(python, physical_type)
                }) =>
        {
            let line = lines[type_line];
            let newline = if line.ends_with('\n') { "\n" } else { "" };
            Some((
                type_line,
                type_line + 1,
                vec![format!("{typed}{}{newline}", comment(line))],
            ))
        }
        Some(_) => None,
    }
}

/// The line edits of the `columns:` key at `columns_index`, or the conflict that stops them.
pub(crate) fn column_edits(
    request: &ContractSourceRequest,
    lines: &[&str],
    (columns_index, source_end): (usize, usize),
) -> Result<Vec<LineEdit>, String> {
    let python = active_python_text();
    let column_indent = sequence_indent(
        lines,
        (columns_index + 1, source_end),
        indent(lines[columns_index]),
    )
    .unwrap_or(indent(lines[columns_index]) + 2);
    let end = columns_end(lines, columns_index, column_indent, source_end);
    let blocks = column_blocks(lines, (columns_index + 1, end), column_indent);
    let declared = python_dict(
        request
            .columns
            .iter()
            .map(|column| (python_casefold(python, &column.0), column)),
    );
    let physical = python_dict(
        request
            .physical_columns
            .iter()
            .map(|column| (python_casefold(python, &column.0), column)),
    );
    let mut line_edits: Vec<LineEdit> = Vec::new();
    for (name, (declared_name, declared_type)) in &declared {
        let Some((_, block)) = blocks.iter().find(|(key, _)| key == name) else {
            return Err(format!(
                "source column '{declared_name}' has no unambiguous YAML block"
            ));
        };
        match physical.iter().find(|(key, _)| key == name) {
            None if request.overwrite => line_edits.push((block.0, block.1, Vec::new())),
            None => {}
            Some((_, (_, physical_type))) => line_edits.extend(type_edit(
                lines,
                *block,
                (declared_type.as_deref(), physical_type),
                (column_indent, request.overwrite),
            )),
        }
    }
    let mut insertion: Vec<String> = Vec::new();
    for (name, column_type) in &request.physical_columns {
        let key = python_casefold(python, name);
        if !declared.iter().any(|(declared, _)| *declared == key) {
            insertion.extend(column_lines(name, column_type, column_indent));
        }
    }
    if !insertion.is_empty() {
        line_edits.push((end, end, insertion));
    }
    Ok(line_edits)
}
