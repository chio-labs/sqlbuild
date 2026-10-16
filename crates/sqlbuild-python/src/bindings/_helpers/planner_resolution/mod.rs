//! Planner reference resolution with Python adapter rendering callbacks.

mod constants;
mod cursor_bounds;
pub(crate) mod cursor_model;
pub(crate) mod cursor_overrides;
pub(crate) mod cursor_policies;
pub(crate) mod cursor_ranges;
mod cursor_safety;
pub(crate) mod cursor_warnings;
mod cursor_windows;
mod future_safety;
mod locations;
mod maximum_safety;
pub(crate) mod models;
pub(crate) mod orchestration;
mod refs;
pub(crate) mod registration;
mod sources;
mod values;
