//! Project assembly key and result aliases.

use crate::assembly::project::errors::AssemblyError;

/// One step's result, or the error Python's assembly raises there.
pub(crate) type Fact<T> = Result<T, AssemblyError>;

/// A `CompiledObjectKey`: `(resource type, name)`.
pub type ObjectKey = (String, String);
