//! Labels, layouts and layer folders of `sqb rename` and `sqb mv` output.

pub(crate) const RENAME_USAGE: &str =
    "write the target as <model> or <model>.<column>; the model: and column: prefixes are optional";
pub(crate) const MOVE_USAGE: &str = "write the target as <model>; the model: prefix is optional";
pub(crate) const RENAME_SCOPE: &str = "sqb rename renames models and model columns";
pub(crate) const MOVE_SCOPE: &str = "sqb mv moves models";
pub(crate) const TARGET_ERROR_CODE: &str = "C954";
pub(crate) const COLUMN_TARGET_KIND: &str = "column";
pub(crate) const COLUMN_TARGET_SEPARATOR: char = '.';
pub(crate) const MODEL_RESOURCE_TYPE: &str = "model";
pub(crate) const CONTINUE_PREFIX: &str = "\u{2502}   ";
pub(crate) const BLANK_PREFIX: &str = "    ";
pub(crate) const POSITION_WIDTH: usize = 8;
pub(crate) const KIND_WIDTH: usize = 10;
pub(crate) const EXCERPT_LIMIT: usize = 60;
pub(crate) const TREE_BRANCH_GLYPH: &str = "\u{251c}\u{2500}\u{2500}";
pub(crate) const TREE_LAST_GLYPH: &str = "\u{2514}\u{2500}\u{2500}";
pub(crate) const FOLDER_PLACEHOLDER: &str = "<folder>";
pub(crate) const PROJECT_DIR_OPTION: &str = "--project-dir";
pub(crate) const SQL_FILE_SUFFIX: &str = ".sql";
pub(crate) const LAYER_FOLDER_RULE_CODES: [&str; 2] = ["SQBRPROJECT102", "SQBRPROJECT105"];
pub(crate) const MODEL_NAME_LAYER_SEPARATOR: &str = "__";
pub(crate) const MODEL_NAME_LAYER_INDEX: usize = 1;
pub(crate) const MODEL_NAME_PART_COUNTS: [usize; 2] = [3, 4];
/// The folder each name layer belongs under.
pub(crate) const LAYER_FOLDERS: [(&str, &[&str]); 7] = [
    ("stg", &["staging"]),
    ("stg_v", &["staging"]),
    ("int_clean", &["intermediate", "clean"]),
    ("int_enriched", &["intermediate", "enriched"]),
    ("int_v", &["intermediate", "enriched"]),
    ("mart", &["mart"]),
    ("mart_v", &["mart"]),
];
/// The folder each name layer's models sit in, as one contiguous run of path parts.
pub(crate) const CONTIGUOUS_LAYER_FOLDERS: [(&str, &[&str]); 7] = [
    ("stg", &["staging"]),
    ("stg_v", &["staging"]),
    ("int_clean", &["intermediate", "clean"]),
    ("int_enriched", &["intermediate", "enriched"]),
    ("int_v", &["intermediate"]),
    ("mart", &["mart"]),
    ("mart_v", &["mart"]),
];
pub(crate) const CURRENT_DIRECTORY: &str = ".";
