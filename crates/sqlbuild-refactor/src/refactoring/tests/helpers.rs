use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_scan::main::quote_policy::quote_policy;

use crate::refactoring::_helpers::chars::chars;
use crate::refactoring::_helpers::scan_context::ScanContext;
use crate::refactoring::_helpers::text_edits::apply_text_edits;
use crate::refactoring::models::{RefactorError, TextEdit};

pub(super) fn python() -> PythonText {
    python_text((3, 12), "15.0.0").expect("Python 3.12 is supported")
}

pub(super) fn context(dialect: &str) -> ScanContext {
    ScanContext {
        backtick_identifiers: quote_policy(dialect).backtick_identifiers,
        python: python(),
    }
}

/// The text after applying edits.
pub(super) fn applied(text: &str, edits: &[TextEdit]) -> Result<String, RefactorError> {
    Ok(apply_text_edits(&chars(text), edits)?.into_iter().collect())
}

/// Each edit as `line:column kind before -> after`, the way the output tree shows it.
pub(super) fn described(edits: &[TextEdit]) -> Vec<String> {
    edits
        .iter()
        .map(|edit| {
            format!(
                "{}:{} {} {:?} -> {:?}",
                edit.line,
                edit.column,
                edit.kind.value(),
                edit.before,
                edit.after
            )
        })
        .collect()
}

/// The texts of spans of `text`.
pub(super) fn span_texts(text: &str, spans: &[(usize, usize)]) -> Vec<String> {
    let characters = chars(text);
    spans
        .iter()
        .map(|(start, end)| characters[*start..*end].iter().collect())
        .collect()
}
