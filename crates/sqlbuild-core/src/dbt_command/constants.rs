//! dbt interop option names and setup layout.

pub const JSON_OPTION: &str = "--json";
pub const VERBOSE_OPTIONS: [&str; 2] = ["--verbose", "-v"];
pub const NO_CONNECTION_OPTION: &str = "--no-connection";
pub const PROJECT_DIR_OPTION: &str = "--project-dir";
pub const PROFILES_DIR_OPTION: &str = "--profiles-dir";
pub const TARGET_OPTION: &str = "--target";
/// Value flags whose paths are re-rooted when a twin project is created.
pub const PATH_VALUE_OPTIONS: [&str; 3] = ["--project-dir", "--profiles-dir", "--target-path"];
/// The twin project directory created next to the dbt project.
pub const TWIN_PROJECT_DIR: &str = "sqlbuild_project";
pub const DBT_PROJECT_FILE: &str = "dbt_project.yml";
pub(crate) const FIELD_LABEL_WIDTH: usize = 25;
