//! Type aliases of the declaration file collections.

use crate::declaration_files::models::{CollectionFailure, ScopedFile};

/// Every file of one collection in Python's order, or the collection's failure.
pub type Collection<T> = Result<Vec<ScopedFile<T>>, CollectionFailure>;
