//! Compiler store directory names and stage capture numbering.

pub(crate) const CACHE_DIRECTORY_NAME: &str = "cache";
pub(crate) const COMPILER_CACHE_DIRECTORY_NAME: &str = "compiler";
/// The namespace suffix of the current native compiler store.
pub(crate) const NATIVE_CACHE_NAMESPACE_SUFFIX: &str = "-native-v1";
/// The namespace suffixes of compiler store roots older releases wrote.
pub(crate) const RETIRED_CACHE_NAMESPACE_SUFFIXES: [&str; 3] =
    ["", "-native-v1", "-native-preview-v1"];
