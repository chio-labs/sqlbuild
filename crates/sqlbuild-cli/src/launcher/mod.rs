//! The `sqb` process: answer `--version`, serve reused compiles natively, hand the rest to Python.

pub(crate) mod _helpers;
pub mod constants;
pub mod main;

#[cfg(test)]
mod tests;
