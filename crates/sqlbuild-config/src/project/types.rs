//! Shared shapes of project configuration loading.

use crate::models::ConfigValue;
use crate::project::errors::ConfigFailure;

/// The entries of a loaded mapping.
pub type Entries = [(ConfigValue, ConfigValue)];
/// A loading step's result.
pub type Loaded<T> = Result<T, ConfigFailure>;
/// Dataclass fields by name.
pub type Fields = Vec<(&'static str, crate::project::models::Built)>;
