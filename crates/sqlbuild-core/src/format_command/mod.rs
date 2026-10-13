//! `sqb format`: formatter path selectors, authored SQL file collection and result rendering.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
