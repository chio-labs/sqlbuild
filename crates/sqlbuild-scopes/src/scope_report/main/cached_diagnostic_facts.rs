//! One cached diagnostic's report facts.

use crate::scope_cache::models::CachedDiagnostic;
use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::models::QualifiedIdentity;
use crate::scope_report::models::DiagnosticFacts;

/// A diagnostic's facts, with its identities as qualified text.
#[must_use]
pub fn cached_diagnostic_facts(item: CachedDiagnostic) -> DiagnosticFacts {
    DiagnosticFacts {
        code: item.code,
        message: item.message,
        severity: item.severity,
        path: item.path,
        line: item.line,
        column: item.column,
        declaration: item
            .declaration
            .map(|identity| format_identity(&QualifiedIdentity::Declaration(identity))),
        resource: item
            .resource
            .map(|identity| format_identity(&QualifiedIdentity::Resource(identity))),
    }
}
