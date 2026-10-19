//! `diagnostic_row`: the `recall_diagnostics` row of one diagnostic.

use crate::records::_helpers::ids::diagnostic_record_id;
use crate::records::_helpers::rows::{finish_row, integer, optional_text, text};
use crate::records::models::{DiagnosticInput, RecallRow, RowEnvelope};
use crate::schema::models::Table;

/// The row of `diagnostic`, keyed by invocation and sequence.
#[must_use]
pub fn diagnostic_row(envelope: &RowEnvelope, diagnostic: &DiagnosticInput) -> RecallRow {
    let correlations = &diagnostic.correlations;
    finish_row(
        Table::Diagnostics,
        envelope,
        vec![
            (
                "record_id",
                text(diagnostic_record_id(
                    &envelope.invocation_id,
                    diagnostic.sequence,
                )),
            ),
            ("sequence", integer(diagnostic.sequence)),
            ("occurred_at", text(&diagnostic.occurred_at)),
            ("severity", text(&diagnostic.severity)),
            ("logger", text(&diagnostic.logger)),
            ("source", text(&diagnostic.source)),
            ("message", text(&diagnostic.message)),
            ("fields", text(&diagnostic.fields)),
            (
                "log_stream_id",
                optional_text(diagnostic.log_stream_id.as_deref()),
            ),
            ("run_id", optional_text(correlations.run_id.as_deref())),
            (
                "resource_id",
                optional_text(correlations.resource_id.as_deref()),
            ),
            (
                "resource_attempt_id",
                optional_text(correlations.resource_attempt_id.as_deref()),
            ),
            (
                "operation_id",
                optional_text(correlations.operation_id.as_deref()),
            ),
            (
                "statement_id",
                optional_text(correlations.statement_id.as_deref()),
            ),
        ],
    )
}
