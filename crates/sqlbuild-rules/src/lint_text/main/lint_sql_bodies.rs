//! `lint_sql_bodies`: native SQL lint of expanded bodies, mapped onto authored source.

use std::collections::HashMap;

use serde_json::Value;

use crate::lint_text::_helpers::sql_diagnostics::{
    AuthoredFile, authored_diagnostic, parse_failure, response_diagnostics, without_generated_frame,
};
use crate::lint_text::_helpers::sql_requests::{lint_payload, omitted_select, run_batch};
use crate::lint_text::models::{AuthoredDiagnostic, LintSqlBody, LintSqlOptions};

/// Lint every body once per distinct request and map each diagnostic onto its authored file.
pub fn lint_sql_bodies(
    bodies: &[LintSqlBody],
    files: &[&str],
    options: &LintSqlOptions,
) -> Vec<AuthoredDiagnostic> {
    let omitted: Vec<Option<usize>> = bodies.iter().map(omitted_select).collect();
    let mut payloads: Vec<Value> = Vec::new();
    let mut index_by_request: HashMap<String, usize> = HashMap::new();
    let mut request_of_body: Vec<usize> = Vec::with_capacity(bodies.len());
    for (body, offset) in bodies.iter().zip(&omitted) {
        let payload: Value = lint_payload((body, files[body.file]), *offset, options);
        let key: String = payload.to_string();
        let next: usize = payloads.len();
        let index: usize = *index_by_request.entry(key).or_insert(next);
        if index == next {
            payloads.push(payload);
        }
        request_of_body.push(index);
    }
    let responses: Vec<Result<Vec<Value>, String>> = run_batch(&payloads)
        .map(|responses| responses.iter().map(response_diagnostics).collect())
        .unwrap_or_else(|error| vec![Err(error); payloads.len()]);
    let authored: Vec<AuthoredFile<'_>> = files
        .iter()
        .map(|text| AuthoredFile::new(text, &options.dialect))
        .collect();
    let mut diagnostics: Vec<AuthoredDiagnostic> = Vec::new();
    for ((body, offset), request) in bodies.iter().zip(omitted).zip(request_of_body) {
        let file: &AuthoredFile<'_> = &authored[body.file];
        let raw: Vec<Value> = match &responses[request] {
            Ok(raw) => raw.clone(),
            Err(message) => {
                diagnostics.push(parse_failure(message, body, file));
                continue;
            }
        };
        let raw: Vec<Value> = without_generated_frame(raw, body, offset);
        for item in &raw {
            match authored_diagnostic(item, body, file) {
                Ok(Some(diagnostic)) => diagnostics.push(diagnostic),
                Ok(None) => {}
                Err(message) => diagnostics.push(parse_failure(&message, body, file)),
            }
        }
    }
    diagnostics
}
