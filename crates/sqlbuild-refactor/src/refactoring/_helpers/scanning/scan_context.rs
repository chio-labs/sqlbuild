//! The lexical settings every SQL scan of one refactoring shares.

use sqlbuild_sqltext::sql_scan::main::quote_policy::quote_policy;

use crate::refactoring::models::RefactorFacts;

/// The dialect's quote policy.
#[derive(Clone, Copy, Debug)]
pub(crate) struct ScanContext {
    pub(crate) backtick_identifiers: bool,
}

impl ScanContext {
    /// The scan settings for a project's facts.
    pub(crate) fn for_facts(facts: &RefactorFacts) -> Self {
        Self {
            backtick_identifiers: quote_policy(&facts.dialect).backtick_identifiers,
        }
    }
}
