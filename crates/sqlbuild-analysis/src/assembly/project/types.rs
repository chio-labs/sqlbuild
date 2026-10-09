//! Project assembly key and result aliases.

/// One step's result, or the deferral kind Python must assemble the project for.
pub(crate) type Fact<T> = Result<T, String>;

/// A `CompiledObjectKey`: `(resource type, name)`.
pub type ObjectKey = (String, String);
