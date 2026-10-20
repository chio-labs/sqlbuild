//! A model's effective config: its layers merged, templated and checked, as `build_model_config` builds it.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
