//! `explain_scope_declaration`: a qualified declaration in an optional resource or path context.

use crate::scope_index::models::ResourceRecord;
use crate::scope_report::_helpers::context::Context;
use crate::scope_report::_helpers::targets::explain_declaration;
use crate::scope_report::_helpers::targets::{prospective_resource, query, resource_matches};
use crate::scope_report::models::{
    DiagnosticFacts, ExplainRequest, Explanation, ReportFailure, ReportSource,
};

/// The explanation and its diagnostics, or the path or identity error Python raises.
pub fn explain_scope_declaration(
    source: ReportSource<'_>,
    request: &ExplainRequest,
) -> Result<(Explanation, Vec<DiagnosticFacts>), ReportFailure> {
    let context: Context<'_> = Context::new(source);
    let mut diagnostics: Vec<DiagnosticFacts> = Vec::new();
    let mut at: Option<ResourceRecord> = None;
    if let Some(path) = &request.at {
        let (_resource, record, raised) = prospective_resource(&context, path, request.directory)?;
        at = record;
        diagnostics = raised;
    } else if let Some(target) = &request.target {
        let matches: Vec<usize> = resource_matches(query(&context, target)?);
        if let [position] = matches.as_slice() {
            at = Some(context.resource(*position).clone());
        }
    }
    let (explanation, explained) =
        explain_declaration(&context, &request.declaration, at.as_ref())?;
    diagnostics.extend(explained);
    Ok((explanation, diagnostics))
}
