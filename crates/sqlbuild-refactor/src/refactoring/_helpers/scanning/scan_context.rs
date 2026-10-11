//! The lexical settings every SQL scan of one refactoring shares.

use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_scan::main::quote_policy::quote_policy;

use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::RefactorFacts;

/// The dialect's quote policy and the Python string semantics of the host.
#[derive(Clone, Copy, Debug)]
pub(crate) struct ScanContext {
    pub(crate) backtick_identifiers: bool,
    pub(crate) python: PythonText,
}

impl ScanContext {
    /// The scan settings for a project's facts, or a deferral for an unknown Python.
    pub(crate) fn for_facts(facts: &RefactorFacts) -> Result<Self, RefactorError> {
        let python =
            python_text(facts.python_version, &facts.unicode_version).ok_or_else(|| {
                RefactorError::internal(format!(
                    "native refactoring does not support Python {}.{} with Unicode {}",
                    facts.python_version.0, facts.python_version.1, facts.unicode_version
                ))
            })?;
        Ok(Self {
            backtick_identifiers: quote_policy(&facts.dialect).backtick_identifiers,
            python,
        })
    }
}
