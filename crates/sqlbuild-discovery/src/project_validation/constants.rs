//! Names and limits cross-file discovery validation checks against.

/// The prefix discovery strips from model paths before matching path defaults.
pub(crate) const MODELS_PREFIX: &str = "models/";
/// `str(Path(...).parent)` of a path with no folder.
pub(crate) const CURRENT_DIRECTORY: &str = ".";
/// How many known model folders an unmatched path default lists.
pub(crate) const KNOWN_FOLDER_LIMIT: usize = 5;
/// Model names SQLBuild reserves for compiled output structure.
pub(crate) const RESERVED_MODEL_NAMES: [&str; 1] = ["_chain_"];
