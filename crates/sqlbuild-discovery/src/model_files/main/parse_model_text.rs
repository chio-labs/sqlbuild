//! Parse SQL model contents that are already in memory.

use crate::model_files::_helpers::parsing::parse_model_file;
use crate::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use crate::models::DiscoveryFailure;

/// One model file's parsed contents, named `file_path` in messages.
pub fn parse_model_text(
    file_path: &str,
    contents: String,
    options: &ModelFileOptions,
) -> Result<DiscoveredModelFile, DiscoveryFailure> {
    parse_model_file(file_path, contents, options)
}
