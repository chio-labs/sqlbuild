//! Python rows of macro call sites, splice spans and recorded call events.

use pyo3::PyResult;
use pyo3::exceptions::PyValueError;
use sqlbuild_render::macro_calls::models::{MacroCallEvent, MacroCallSite, MacroSpliceSpan};

/// Event tags shared with `sqlbuild.compiler.macro_bridge.constants`.
const MACRO_USE: u8 = 0;
const DECLARATION_READ: u8 = 1;
const GENERATED_SQL: u8 = 2;
const ARGUMENT_REFERENCE: u8 = 3;

/// One call site: start, end, name, tree names if scanned and whether typed reference text
/// appears.
pub(crate) type SiteRow = (usize, usize, String, Option<Vec<String>>, bool);
/// One substitution span: source start and end, output start and end.
pub(crate) type SpanRow = (usize, usize, usize, usize);
/// One recorded event: its tag and two text fields.
pub(crate) type EventRow = (u8, String, String);
/// One recorded call: its SQL, added relations and events.
pub(crate) type EntryRow = (String, Vec<(String, String)>, Vec<EventRow>);

pub(crate) fn site_row(site: MacroCallSite) -> SiteRow {
    (
        site.start,
        site.end,
        site.name,
        site.tree_names,
        site.typed_reference_text,
    )
}

pub(crate) fn span_row(span: MacroSpliceSpan) -> SpanRow {
    (
        span.source_start,
        span.source_end,
        span.output_start,
        span.output_end,
    )
}

pub(crate) fn event_row(event: &MacroCallEvent) -> EventRow {
    match event {
        MacroCallEvent::MacroUse { name } => (MACRO_USE, name.clone(), String::new()),
        MacroCallEvent::DeclarationRead { kind, name } => {
            (DECLARATION_READ, kind.clone(), name.clone())
        }
        MacroCallEvent::GeneratedSql { macro_name, sql } => {
            (GENERATED_SQL, macro_name.clone(), sql.clone())
        }
        MacroCallEvent::ArgumentReference { kind, name } => {
            (ARGUMENT_REFERENCE, kind.clone(), name.clone())
        }
    }
}

pub(crate) fn event_from_row((tag, first, second): EventRow) -> PyResult<MacroCallEvent> {
    match tag {
        MACRO_USE => Ok(MacroCallEvent::MacroUse { name: first }),
        DECLARATION_READ => Ok(MacroCallEvent::DeclarationRead {
            kind: first,
            name: second,
        }),
        GENERATED_SQL => Ok(MacroCallEvent::GeneratedSql {
            macro_name: first,
            sql: second,
        }),
        ARGUMENT_REFERENCE => Ok(MacroCallEvent::ArgumentReference {
            kind: first,
            name: second,
        }),
        _ => Err(PyValueError::new_err(format!(
            "unknown macro call event tag {tag}"
        ))),
    }
}
