//! dbt options, argv requests, parsed `sqb dbt` flags and config sources.

/// dbt options shared by every dbt command, paths already rendered as text.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtCliOptionValues {
    pub project_dir: Option<String>,
    pub profiles_dir: Option<String>,
    pub target: Option<String>,
    pub target_path: Option<String>,
    pub vars: Option<String>,
    pub state: Option<String>,
    pub defer: bool,
}

/// The dbt command an argv is built for and its command-specific arguments.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DbtArgvCommand {
    Compile {
        full_refresh: bool,
    },
    Deps,
    Debug {
        args: Vec<String>,
    },
    Other {
        command: String,
        args: Vec<String>,
    },
    Ls {
        select: Vec<String>,
        exclude: Vec<String>,
        resource_types: Vec<String>,
    },
}

/// The `sqb dbt` command a routed argument set belongs to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DbtInteropCommandKind {
    Plan,
    Run,
    Build,
    Debug,
}

impl DbtInteropCommandKind {
    /// The command's name on the command line.
    #[must_use]
    pub fn name(self) -> &'static str {
        match self {
            Self::Plan => "plan",
            Self::Run => "run",
            Self::Build => "build",
            Self::Debug => "debug",
        }
    }
}

/// Declared `sqb dbt` flags as parsed, before routing.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtParsedFlags {
    pub select: Vec<String>,
    pub exclude: Vec<String>,
    pub vars: Option<String>,
    pub threads: Option<String>,
    pub full_refresh: bool,
    pub event_time_start: Option<String>,
    pub event_time_end: Option<String>,
    pub project_dir: Option<String>,
    pub profiles_dir: Option<String>,
    pub profile: Option<String>,
    pub target: Option<String>,
    pub target_path: Option<String>,
    pub state: Option<String>,
    pub indirect_selection: Option<String>,
    pub defer: bool,
    pub start_cursor_ts: Option<String>,
    pub end_cursor_ts: Option<String>,
    pub start_cursor_int: Option<String>,
    pub end_cursor_int: Option<String>,
    pub defer_to: Option<String>,
    pub fail_fast: bool,
    pub hard_copy: bool,
    pub dbt_passthrough: Vec<String>,
}

/// Parsed flags split into the dbt and SQLBuild argument buckets.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtRoutedArgs {
    pub dbt_args: Vec<String>,
    pub sqlbuild_args: Vec<String>,
}

/// One dbt setting from a CLI override and project config, plus a local override for `target`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtConfigSources {
    pub override_project_dir: Option<String>,
    pub config_project_dir: Option<String>,
    pub override_profiles_dir: Option<String>,
    pub config_profiles_dir: Option<String>,
    pub override_target_path: Option<String>,
    pub config_target_path: Option<String>,
    pub override_target: Option<String>,
    pub local_target: Option<String>,
    pub config_target: Option<String>,
}

/// The raw dbt setting values that apply, paths still unresolved.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtConfigChoice {
    pub project_dir: Option<String>,
    pub profiles_dir: Option<String>,
    pub target_path: Option<String>,
    pub target: Option<String>,
}
