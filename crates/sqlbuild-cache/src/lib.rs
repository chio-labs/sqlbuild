//! The shared native cache store and the content fingerprints its keys are built from.

#![forbid(unsafe_code)]

pub mod artifacts;
pub mod digest;
pub mod hosted_shapes;
pub mod macro_store_keys;
pub mod module_digests;
pub mod project_reuse;
pub mod project_snapshot;
pub mod stage_capture;
pub mod startup_inputs;
pub mod store;
