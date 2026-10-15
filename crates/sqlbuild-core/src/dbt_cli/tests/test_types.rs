use crate::dbt_cli::errors::DbtCliError;
use crate::dbt_cli::models::{DbtConfigChoice, DbtInteropCommandKind, DbtRoutedArgs};

pub(super) struct ArgvTestCase {
    pub(super) description: &'static str,
    pub(super) argv: Vec<String>,
    pub(super) expected_argv: Vec<&'static str>,
}

pub(super) struct RouteTestCase {
    pub(super) description: &'static str,
    pub(super) routed: Result<(DbtInteropCommandKind, DbtRoutedArgs), DbtCliError>,
    pub(super) expected_dbt_args: Vec<&'static str>,
    pub(super) expected_sqlbuild_args: Vec<&'static str>,
    pub(super) expected_error: Option<(&'static str, &'static str)>,
}

pub(super) struct ConfigTestCase {
    pub(super) description: &'static str,
    pub(super) choice: Result<DbtConfigChoice, DbtCliError>,
    pub(super) expected_choice: Result<DbtConfigChoice, &'static str>,
}

pub(super) struct FlagValueTestCase {
    pub(super) description: &'static str,
    pub(super) args: &'static [&'static str],
    pub(super) flag: &'static str,
    pub(super) expected_value: Option<&'static str>,
}
