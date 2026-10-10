//! The compile's natively owned project: facts each producer retains for every consumer.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
