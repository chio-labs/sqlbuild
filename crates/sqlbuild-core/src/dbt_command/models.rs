//! dbt command arguments and setup results as the command reads and reports them.

/// The SQLBuild output flags found in forwarded dbt arguments, and the arguments without them.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtOutputOptions {
    pub json_output: bool,
    pub verbose: bool,
    pub routed_args: Vec<String>,
}

/// One forwarded argument: kept as written, or a path value to re-root.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ForwardedArg {
    Literal(String),
    Path(String),
}

/// A created or previewed SQLBuild twin project.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtInitSummary {
    pub output_dir: String,
    pub project_file: String,
    pub project_name: String,
    pub adapter: String,
    pub target_name: String,
    pub profile_name: String,
    pub toml: String,
}
