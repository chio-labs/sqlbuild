//! The Recall writer: a bounded priority queue fed by producers and drained by one delivery thread that alone owns the store connection.

pub(crate) mod _helpers;
pub mod constants;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
