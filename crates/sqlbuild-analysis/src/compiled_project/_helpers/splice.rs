//! Replacing scanned declaration references, indexed by character as Python strings are.

use crate::compiled_project::models::{DeclarationSplice, SplicedSpan, SplicedSql};

pub(crate) fn splice_declarations(sql: &str, splices: &[DeclarationSplice]) -> SplicedSql {
    if sql.is_ascii() {
        return spliced(sql.len(), splices, |output, start, end| {
            output.push_str(&sql[start..end]);
        });
    }
    let characters: Vec<char> = sql.chars().collect();
    spliced(characters.len(), splices, |output, start, end| {
        output.extend(&characters[start..end]);
    })
}

/// The splice over text of `length` characters, `copy` appending each kept character range.
fn spliced(
    length: usize,
    splices: &[DeclarationSplice],
    copy: impl Fn(&mut String, usize, usize),
) -> SplicedSql {
    let mut output: String = String::with_capacity(length);
    let mut spans: Vec<SplicedSpan> = Vec::with_capacity(splices.len());
    let mut cursor: usize = 0;
    let mut output_length: usize = 0;
    for splice in splices {
        copy(&mut output, cursor, splice.start);
        output_length += splice.start - cursor;
        let replacement_length: usize = splice.replacement.chars().count();
        output.push_str(&splice.replacement);
        spans.push(SplicedSpan {
            source_start: splice.start,
            source_end: splice.end,
            output_start: output_length,
            output_end: output_length + replacement_length,
        });
        output_length += replacement_length;
        cursor = splice.end;
    }
    copy(&mut output, cursor, length);
    SplicedSql { sql: output, spans }
}

pub(crate) fn merge_call_site_references<T: PartialEq>(
    references: Vec<T>,
    arguments: Vec<T>,
) -> Vec<T> {
    if arguments.is_empty() {
        return references;
    }
    let mut merged: Vec<T> = Vec::with_capacity(references.len() + arguments.len());
    for reference in references.into_iter().chain(arguments) {
        if !merged.contains(&reference) {
            merged.push(reference);
        }
    }
    merged
}

/// An enum member's SQL literal: integers as written, text single-quoted with quotes doubled.
pub(crate) fn enum_member_literal(text: &str, integer: bool) -> String {
    if integer {
        return text.to_owned();
    }
    format!("'{}'", text.replace('\'', "''"))
}
