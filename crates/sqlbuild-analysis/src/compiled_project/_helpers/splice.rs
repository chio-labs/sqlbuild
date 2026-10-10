//! Replacing scanned declaration references, indexed by character as Python strings are.

use crate::compiled_project::models::{DeclarationSplice, SplicedSpan, SplicedSql};

pub(crate) fn splice_declarations(sql: &str, splices: &[DeclarationSplice]) -> SplicedSql {
    let characters: Vec<char> = sql.chars().collect();
    let mut output: String = String::with_capacity(sql.len());
    let mut spans: Vec<SplicedSpan> = Vec::with_capacity(splices.len());
    let mut cursor: usize = 0;
    let mut output_length: usize = 0;
    for splice in splices {
        output.extend(&characters[cursor..splice.start]);
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
    output.extend(&characters[cursor..]);
    SplicedSql { sql: output, spans }
}

/// An enum member's SQL literal: integers as written, text single-quoted with quotes doubled.
pub(crate) fn enum_member_literal(text: &str, integer: bool) -> String {
    if integer {
        return text.to_owned();
    }
    format!("'{}'", text.replace('\'', "''"))
}
