//! A model's binding diagnostics at their authored locations, deduplicated as compile reports.

use std::collections::HashSet;

use crate::binding_locations::constants::{ERROR_SEVERITY, UNKNOWN_TABLE_INTERNAL_CODE};
use crate::binding_locations::models::{AuthoredSpan, BindingSource, LocatedDiagnostic};
use crate::semantic_validation::models::{BindingPositions, PositionInput};
use crate::semantic_validation::types::DiagnosticRow;

/// Each reported diagnostic in order; an error mapping a position is the mapper's message.
pub fn locate_binding_diagnostics(
    rows: &[DiagnosticRow],
    source: &BindingSource<'_>,
) -> Result<Vec<LocatedDiagnostic>, String> {
    let line_offset: Option<usize> = source
        .authored
        .find(source.query)
        .map(|start| source.authored[..start].matches('\n').count());
    let mut positions: Option<BindingPositions> = None;
    let mut seen: HashSet<(String, String, Option<usize>, Option<usize>)> = HashSet::new();
    let mut located: Vec<LocatedDiagnostic> = Vec::new();
    for (code, message, line, column, start, end, severity) in rows {
        if code == UNKNOWN_TABLE_INTERNAL_CODE {
            continue;
        }
        let mapper: &BindingPositions = match &mut positions {
            Some(mapper) => mapper,
            slot @ None => slot.insert(BindingPositions::new(position_input(source))?),
        };
        let location: Option<AuthoredSpan> =
            authored_span(mapper, (*start, *line, *column), *end, message)?;
        let (line, column) = match location {
            Some(span) => (Some(span.line), Some(span.column)),
            None => (
                match (line, line_offset) {
                    (Some(line), Some(offset)) => Some(line + offset),
                    (line, _) => *line,
                },
                *column,
            ),
        };
        let key = (code.clone(), message.clone(), line, column);
        if seen.contains(&key) && start.is_some() && severity == ERROR_SEVERITY {
            continue;
        }
        seen.insert(key);
        located.push(LocatedDiagnostic {
            code: code.clone(),
            message: message.clone(),
            severity: severity.clone(),
            line,
            column,
            location,
        });
    }
    Ok(located)
}

fn position_input(source: &BindingSource<'_>) -> PositionInput {
    let (expanded, passes) = source.expansion.unwrap_or((source.query, &[]));
    PositionInput {
        authored: source.authored.to_owned(),
        query: source.query.to_owned(),
        expanded: expanded.to_owned(),
        cleaned: source.cleaned.to_owned(),
        passes: passes.to_vec(),
    }
}

/// `get_authored_binding_location`: the start, and the end when the diagnostic spans one.
fn authored_span(
    mapper: &BindingPositions,
    (start, line, column): (Option<usize>, Option<usize>, Option<usize>),
    end: Option<usize>,
    message: &str,
) -> Result<Option<AuthoredSpan>, String> {
    let (Some(line), Some(column)) = mapper.position(start, line, column, message)? else {
        return Ok(None);
    };
    let (end_line, end_column) = match end {
        Some(end) => mapper.position(Some(end), None, None, "")?,
        None => (None, None),
    };
    Ok(Some(AuthoredSpan {
        line,
        column,
        end_line,
        end_column,
    }))
}
