//! The invocation services a parsed command runs with.

use crate::dispatch::constants::{
    DBT_COMMAND_NAME, DBT_INIT_SUBCOMMAND, DIFF_COMMAND_NAME, PROJECT_CREATING_COMMANDS,
    SKILL_EXEMPT_COMMANDS,
};
use crate::dispatch::models::{CommandFacts, InvocationPolicy};

/// Whether the command creates a project, is observed, and checks skill freshness.
#[must_use]
pub fn invocation_policy(facts: &CommandFacts) -> InvocationPolicy {
    let command: &str = facts.command.as_deref().unwrap_or_default();
    let creates_project: bool = PROJECT_CREATING_COMMANDS.contains(&command)
        || (command == DBT_COMMAND_NAME
            && facts.subcommand.as_deref() == Some(DBT_INIT_SUBCOMMAND));
    let raw_query_diff: bool = command == DIFF_COMMAND_NAME && facts.raw_query_diff;
    InvocationPolicy {
        creates_project,
        observed: !creates_project && !raw_query_diff,
        maintains_skills: !SKILL_EXEMPT_COMMANDS.contains(&command) && !raw_query_diff,
    }
}
