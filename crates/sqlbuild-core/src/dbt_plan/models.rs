//! Plan command-line inputs and outputs.

use crate::dbt_cli::models::{DbtCliOptionValues, DbtInteropCommandKind};

/// What the plan's dbt and SQLBuild command lines are built from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DbtPlanArgvRequest<'a> {
    pub command: DbtInteropCommandKind,
    pub dbt_executable: &'a str,
    pub sqlbuild_executable: &'a str,
    pub options: &'a DbtCliOptionValues,
    pub dbt_command_args: &'a [String],
    pub sqlbuild_command_args: &'a [String],
    pub selected_model_names: &'a [String],
    pub required_selector_terms: &'a [String],
}

/// The primary dbt command, the SQLBuild commands and the supplemental dbt commands.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtPlanArgvs {
    pub dbt_command_argv: Vec<String>,
    pub sqlbuild_command_argvs: Vec<Vec<String>>,
    pub supplemental_dbt_command_argvs: Vec<Vec<String>>,
}

/// One dbt model a selected SQLBuild model references.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtReferencedModel {
    pub unique_id: String,
    pub fqn: Vec<String>,
    pub name: String,
}

/// One executed dbt node's outcome.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DbtExecutedNode {
    pub unique_id: String,
    pub resource_type: String,
    pub status: String,
    pub execution_time: Option<f64>,
}
