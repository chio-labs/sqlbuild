//! SQLBuild-owned generic SQL linting over the external Polyglot parser.

pub(crate) mod engine;
pub(crate) mod formatter;
mod models;

#[cfg(test)]
mod tests;
