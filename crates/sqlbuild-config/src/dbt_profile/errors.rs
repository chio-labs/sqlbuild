//! A dbt profile SQLBuild cannot connect with.

/// `DbtProfileError(message)`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DbtProfileError(pub String);
