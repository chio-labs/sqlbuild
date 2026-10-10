//! Explicit-reference key aliases.

/// A `CompiledObjectKey`: `(resource type, name)`; typed SQL refs use the same kind names.
pub type ResourceKey = (String, String);
