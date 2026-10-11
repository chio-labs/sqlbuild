//! Locating a reference-scan fault of expanded model SQL in the authored model file.

use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_sqltext::compiler::main::model_header_matching::match_batch;
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{ReferenceExtraction, ReferenceScanFailure};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiled_project::_helpers::sources::char_position;
use crate::compiled_project::models::{ScanFaultOrigin, SplicedSpan};

/// `_located_scan_error`'s message: `path:line:column: message`, or `path: message`.
pub(crate) fn located_scan_error(
    failure: &ReferenceScanFailure,
    sql: &str,
    origin: &ScanFaultOrigin<'_>,
    syntax: &LexicalSyntax,
) -> String {
    let path: &str = origin.relative_path;
    match authored_fault_offset(failure, sql, origin, syntax) {
        Some(offset) => {
            let contents: Vec<char> = origin.contents.chars().collect();
            let position = char_position(&contents, offset);
            format!(
                "{path}:{}:{}: {}",
                position.line, position.column, failure.message
            )
        }
        None => format!("{path}: {}", failure.message),
    }
}

fn authored_fault_offset(
    failure: &ReferenceScanFailure,
    sql: &str,
    origin: &ScanFaultOrigin<'_>,
    syntax: &LexicalSyntax,
) -> Option<usize> {
    let contents: Vec<char> = origin.contents.chars().collect();
    let passes: &[Vec<SplicedSpan>] = origin.passes.as_deref()?;
    let sql_characters: Vec<char> = sql.chars().collect();
    let start: usize = failure.start;
    let body_start: usize = model_query_start(origin.contents, origin.query_sql)?;
    if start >= sql_characters.len() {
        return None;
    }
    let (mapped, generated) = map_through_passes(start, passes);
    let authored: usize = body_start + mapped;
    if generated || authored >= contents.len() || contents[authored] != sql_characters[start] {
        return None;
    }
    let mut blanked: Vec<char> = sql_characters;
    for (output_start, output_end) in expansion_output_ranges(passes) {
        let length: usize = blanked.len();
        let from: usize = output_start.min(length);
        let to: usize = output_end.min(length).max(from);
        let spaces = std::iter::repeat_n(' ', output_end.saturating_sub(output_start));
        blanked.splice(from..to, spaces);
    }
    let blanked: String = blanked.into_iter().collect();
    match extract_sql_references(&blanked, syntax) {
        ReferenceExtraction::Failed(rescanned) if rescanned == *failure => Some(authored),
        _ => None,
    }
}

/// `get_model_query_start`: where the stripped query starts after the MODEL header, if it does.
pub(crate) fn model_query_start(contents: &str, query_sql: &str) -> Option<usize> {
    let (_, _, sql_start) = match_batch(&[contents.to_owned()]).pop().flatten()?;
    let characters: Vec<char> = contents.chars().collect();
    let mut start: usize = sql_start;
    while start < characters.len() && is_python_space(characters[start]) {
        start += 1;
    }
    let query: Vec<char> = query_sql.chars().collect();
    characters[start..].starts_with(&query).then_some(start)
}

/// `map_through_passes`: the offset in the first pass's source, and whether expansion made it.
pub(crate) fn map_through_passes(offset: usize, passes: &[Vec<SplicedSpan>]) -> (usize, bool) {
    let mut current: usize = offset;
    let mut generated: bool = false;
    for spans in passes.iter().rev() {
        let (mapped, made) = map_output_offset(current, spans);
        current = mapped;
        generated |= made;
    }
    (current, generated)
}

fn map_output_offset(offset: usize, spans: &[SplicedSpan]) -> (usize, bool) {
    let mut mapped: isize = to_signed(offset);
    for span in spans {
        if offset < span.output_start {
            break;
        }
        if offset < span.output_end {
            return (span.source_start, true);
        }
        mapped += to_signed(span.source_end)
            - to_signed(span.source_start)
            - (to_signed(span.output_end) - to_signed(span.output_start));
    }
    (usize::try_from(mapped).unwrap_or_default(), false)
}

/// `_expansion_output_ranges`: every expansion's output range in the final pass's output.
pub(crate) fn expansion_output_ranges(passes: &[Vec<SplicedSpan>]) -> Vec<(usize, usize)> {
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    for (index, spans) in passes.iter().enumerate() {
        for span in spans {
            let mut output_start: usize = span.output_start;
            let mut output_end: usize = span.output_end;
            for later in &passes[index + 1..] {
                output_start = later_pass_offset(output_start, later, false);
                output_end = later_pass_offset(output_end, later, true);
            }
            ranges.push((output_start, output_end));
        }
    }
    ranges
}

fn later_pass_offset(offset: usize, spans: &[SplicedSpan], end: bool) -> usize {
    let mut shift: isize = 0;
    for span in spans {
        if offset < span.source_start || (end && offset == span.source_start) {
            break;
        }
        if offset < span.source_end || (end && offset == span.source_end) {
            return if end {
                span.output_end
            } else {
                span.output_start
            };
        }
        shift += to_signed(span.output_end)
            - to_signed(span.output_start)
            - (to_signed(span.source_end) - to_signed(span.source_start));
    }
    usize::try_from(to_signed(offset) + shift).unwrap_or_default()
}

fn to_signed(value: usize) -> isize {
    isize::try_from(value).unwrap_or(isize::MAX)
}
