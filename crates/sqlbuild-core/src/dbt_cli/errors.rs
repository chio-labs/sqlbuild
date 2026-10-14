//! Invalid `sqb dbt` arguments and configuration.

/// A rejected argument combination or missing setting, with its diagnostic code and help.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtCliError {
    pub message: String,
    pub code: Option<&'static str>,
    pub help: Option<&'static str>,
}
