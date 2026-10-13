//! `sqb`'s argument parsing: an `argparse`-compatible parser over the embedded command table.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
