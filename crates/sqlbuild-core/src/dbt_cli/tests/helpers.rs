use crate::dbt_cli::errors::DbtCliError;
use crate::dbt_cli::models::{DbtCliOptionValues, DbtInteropCommandKind, DbtRoutedArgs};

pub(super) fn text(value: &str) -> Option<String> {
    Some(value.to_owned())
}

pub(super) fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// Options with every common setting set.
pub(super) fn full_options() -> DbtCliOptionValues {
    DbtCliOptionValues {
        project_dir: text("/repo/dbt"),
        profiles_dir: text("/repo/profiles"),
        target: text("prod"),
        target_path: text("/repo/target"),
        vars: text("{}"),
        state: text("/repo/state"),
        defer: true,
    }
}

/// The routed buckets as text, or empty buckets on failure.
pub(super) fn buckets(
    routed: &Result<(DbtInteropCommandKind, DbtRoutedArgs), DbtCliError>,
) -> (Vec<&str>, Vec<&str>) {
    routed.as_ref().map_or_else(
        |_| (Vec::new(), Vec::new()),
        |(_, args)| {
            (
                args.dbt_args.iter().map(String::as_str).collect(),
                args.sqlbuild_args.iter().map(String::as_str).collect(),
            )
        },
    )
}

/// The failure message and code, when routing failed.
pub(super) fn failure(
    routed: &Result<(DbtInteropCommandKind, DbtRoutedArgs), DbtCliError>,
) -> Option<(&str, &str)> {
    routed
        .as_ref()
        .err()
        .map(|error| (error.message.as_str(), error.code.unwrap_or_default()))
}
