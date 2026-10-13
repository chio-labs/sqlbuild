//! The value following a flag in forwarded dbt arguments.

/// The argument after the first occurrence of `flag`, when there is one.
#[must_use]
pub fn dbt_value_arg(args: &[String], flag: &str) -> Option<String> {
    let index: usize = args.iter().position(|arg| arg == flag)?;
    args.get(index + 1).cloned()
}
