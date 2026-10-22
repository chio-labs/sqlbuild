//! The invocation services a parsed command runs with.

use crate::dispatch::constants::{
    DBT_COMMAND_NAME, DBT_INIT_SUBCOMMAND, DIFF_COMMAND_NAME, PROJECT_CREATING_COMMANDS,
    RECALL_COMMAND_NAME, SKILL_EXEMPT_COMMANDS,
};
use crate::dispatch::models::{CommandFacts, InvocationPolicy};

/// Whether the command creates a project, is observed, checks skill freshness, is recorded and has its streams captured; only observed commands are recorded, so every recorded invocation has terminal events. `sqb recall` only reads history, so it publishes no lifecycle events, runs no sinks and keeps no compute logs.
#[must_use]
pub fn invocation_policy(facts: &CommandFacts) -> InvocationPolicy {
    let command: &str = facts.command.as_deref().unwrap_or_default();
    let creates_project: bool = PROJECT_CREATING_COMMANDS.contains(&command)
        || (command == DBT_COMMAND_NAME
            && facts.subcommand.as_deref() == Some(DBT_INIT_SUBCOMMAND));
    let raw_query_diff: bool = command == DIFF_COMMAND_NAME && facts.raw_query_diff;
    let reads_history: bool = command == RECALL_COMMAND_NAME;
    let observed: bool = !creates_project && !raw_query_diff && !reads_history;
    InvocationPolicy {
        creates_project,
        observed,
        maintains_skills: !SKILL_EXEMPT_COMMANDS.contains(&command) && !raw_query_diff,
        recalled: observed && !command.is_empty(),
        captured: !creates_project && !reads_history,
    }
}
