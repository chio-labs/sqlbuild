//! `invocation_row`: the `recall_invocations` context row.

use crate::records::_helpers::rows::{boolean, finish_row, integer, optional_text, text};
use crate::records::models::{InvocationContext, RecallRow, RecallValue, RowEnvelope};
use crate::schema::models::Table;

fn json_list(items: &[String]) -> RecallValue {
    text(serde_json::Value::from(items.to_vec()).to_string())
}

/// The context row of one invocation.
#[must_use]
pub fn invocation_row(envelope: &RowEnvelope, context: &InvocationContext) -> RecallRow {
    finish_row(
        Table::Invocations,
        envelope,
        vec![
            ("command", optional_text(context.command.as_deref())),
            ("subcommand", optional_text(context.subcommand.as_deref())),
            ("selection", json_list(&context.selection)),
            ("exclusion", json_list(&context.exclusion)),
            (
                "project_name",
                optional_text(context.project_name.as_deref()),
            ),
            (
                "project_dir_hash",
                optional_text(context.project_dir_hash.as_deref()),
            ),
            ("target", optional_text(context.target.as_deref())),
            ("adapter", optional_text(context.adapter.as_deref())),
            (
                "destination_database",
                optional_text(context.destination_database.as_deref()),
            ),
            (
                "destination_schema",
                optional_text(context.destination_schema.as_deref()),
            ),
            (
                "destination_fingerprint",
                optional_text(context.destination_fingerprint.as_deref()),
            ),
            (
                "sqlbuild_version",
                optional_text(context.sqlbuild_version.as_deref()),
            ),
            (
                "git_revision",
                optional_text(context.git_revision.as_deref()),
            ),
            (
                "git_dirty",
                context.git_dirty.map_or(RecallValue::Null, boolean),
            ),
            ("host_token", optional_text(context.host_token.as_deref())),
            (
                "pid",
                context
                    .pid
                    .map_or(RecallValue::Null, |pid| integer(u64::from(pid))),
            ),
            (
                "external_context",
                optional_text(context.external_context.as_deref()),
            ),
            (
                "recall_filter_active",
                boolean(context.recall_filter_active),
            ),
            ("argv_digest", optional_text(context.argv_digest.as_deref())),
            ("origin", optional_text(context.origin.as_deref())),
            (
                "command_mode",
                optional_text(context.command_mode.as_deref()),
            ),
        ],
    )
}
