//! SQLBuild-owned generic SQL linting over the external Polyglot parser.

pub(crate) mod _helpers;
mod constants;
pub(crate) mod main;
mod models;

#[cfg(test)]
mod tests;
