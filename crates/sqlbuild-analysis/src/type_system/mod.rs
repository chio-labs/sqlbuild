//! Type normalization and type equality shared by every analysis stage.

pub(crate) mod _helpers;
mod constants;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
