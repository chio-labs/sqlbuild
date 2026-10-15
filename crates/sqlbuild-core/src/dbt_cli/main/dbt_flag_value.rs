//! The value after a dbt flag in routed dbt arguments.

/// The argument after the first exact `flag`, when there is one.
#[must_use]
pub fn dbt_flag_value(args: &[String], flag: &str) -> Option<String> {
    let index: usize = args.iter().position(|arg| arg == flag)?;
    args.get(index + 1).cloned()
}
