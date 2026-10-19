//! `artifact_rows`: the content row of one artifact and the reference row naming it.

use crate::records::_helpers::rows::{finish_row, integer, optional_text, text};
use crate::records::models::{ArtifactInput, RecallRow, RecallValue, RowEnvelope};
use crate::schema::models::Table;

/// `[recall_artifacts row, recall_artifact_refs row]`, written in one batch so retention never sees the content without its reference.
#[must_use]
pub fn artifact_rows(envelope: &RowEnvelope, artifact: &ArtifactInput) -> [RecallRow; 2] {
    [
        finish_row(
            Table::Artifacts,
            envelope,
            vec![
                ("digest", text(&artifact.digest)),
                ("kind", text(&artifact.kind)),
                ("media_type", text(&artifact.media_type)),
                ("size", integer(artifact.content.len() as u64)),
                ("content", RecallValue::Blob(artifact.content.clone())),
                ("seen_at", text(&artifact.seen_at)),
            ],
        ),
        finish_row(
            Table::ArtifactRefs,
            envelope,
            vec![
                ("digest", text(&artifact.digest)),
                ("ref_id", text(&artifact.ref_id)),
                (
                    "statement_id",
                    optional_text(artifact.statement_id.as_deref()),
                ),
                (
                    "resource_id",
                    optional_text(artifact.resource_id.as_deref()),
                ),
                ("role", text(&artifact.role)),
                ("referenced_at", text(&artifact.seen_at)),
            ],
        ),
    ]
}
