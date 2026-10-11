//! Constants of project refactorings, mirroring `sqlbuild.compiler.refactoring.constants`.

pub const MODEL_KIND_PREFIX: &str = "model:";
pub const SQL_SUFFIX: &str = ".sql";
pub const CURRENT_DIRECTORY: &str = ".";
pub const REF_FUNCTION: &str = "__ref";
pub const REF_FIXTURE_PREFIX: &str = "__ref__";
pub const EXPECTED_FIXTURE_PREFIX: &str = "__expected__";
pub const PLACEHOLDER_PAD: char = '_';
pub const GENERIC_PLACEHOLDER_KIND: char = 'x';
pub const ROOT_SCOPE: &str = "root";
pub const CTE_SCOPE_PREFIX: &str = "cte:";
pub const MIGRATE_FROM_KEY: &str = "migrate_from";
pub const CURSOR_INPUTS_KEY: &str = "cursor_inputs";
pub const COLUMNS_KEY: &str = "columns";
pub const RELATIONSHIPS_AUDIT: &str = "relationships";
pub const RELATIONSHIPS_TO_KEY: &str = "to";
pub const RELATIONSHIPS_FIELD_KEY: &str = "field";
pub const COLUMN_VALUED_CONFIG_KEYS: [&str; 9] = [
    "cursor",
    "unique_key",
    "updated_at",
    "check_columns",
    "merge_exclude_columns",
    "partition_by",
    "cluster_by",
    "observed_at",
    "row_diff_exclude_columns",
];
pub const HISTORY_MATERIALIZATIONS: [&str; 2] = ["incremental", "snapshot"];
pub const MIGRATABLE_MATERIALIZATIONS: [&str; 4] = ["table", "view", "incremental", "snapshot"];
pub const COPIED_PROJECT_SUFFIXES: [&str; 7] =
    [".sql", ".py", ".yml", ".yaml", ".toml", ".csv", ".json"];
pub const IGNORED_PROJECT_DIRECTORIES: [&str; 5] =
    ["target", "logs", "venv", "node_modules", "__pycache__"];
pub const PYCACHE_DIRECTORY: &str = "__pycache__";
pub const HIDDEN_PREFIX: &str = ".";
pub const HEADER_DESCRIPTION_KEY: &str = "description";
pub const HEADER_INDENT: &str = "  ";
pub const HEADER_SEPARATOR: &str = ",";
pub const HEADER_OPEN_PAREN: &str = "(";
pub const HEADER_OPENERS: [&str; 3] = ["(", "[", "{"];
pub const HEADER_CLOSERS: [&str; 3] = [")", "]", "}"];
pub const PARENTHESIZED_EMPTY_TOKENS: usize = 2;
pub const HEADER_KEY_AND_VALUE_TOKENS: usize = 2;
pub const REF_KIND: &str = "ref";
pub const SOURCE_KIND: &str = "source";
pub const SEED_KIND: &str = "seed";
pub const MODEL_RESOURCE_TYPE: &str = "model";
pub const UNKNOWN_COLUMN_TYPE: &str = "UNKNOWN";
pub const GENERIC_DIALECT: &str = "generic";
pub const SCHEMA_KEYWORD: &str = "SCHEMA";
pub const MODEL_MANUAL_HELP: &str = "Pass the model into the macro as an argument, or edit the listed locations, then run the command again.";
pub const COLUMN_MANUAL_HELP: &str = "Edit the listed locations, then run the command again.";
/// `RefactorInputError`'s default code.
pub const INPUT_ERROR_CODE: &str = "C950";
/// `RefactorEditError`'s code: two planned edits overlap.
pub const EDIT_ERROR_CODE: &str = "C957";
/// `RefactorWriteError`'s code: project files changed between planning and writing.
pub const WRITE_ERROR_CODE: &str = "C958";
/// Header whitespace that indents a MODEL `columns` entry.
pub const CONTRACT_HEADER_WHITESPACE: [char; 2] = [' ', '\t'];
pub const CONTRACT_DEFAULT_INDENT: &str = "    ";
pub const CONTRACT_GENERATED_MARKER: &str = "generated";
pub const CONTRACT_GENERATED_MARKER_LINES: usize = 5;
pub const CONTRACT_TYPE_KEY: &str = "type";
pub const CONTRACT_YAML_COLUMNS_KEY: &str = "columns";
pub const CONTRACT_YAML_LIST_NAME: &str = "- name:";
pub const CONTRACT_YAML_COMMENT: &str = " #";
pub const CONTRACT_MODEL_HEADER_ESCAPE: char = '\\';
pub const CONTRACT_HEADER_WORD_EXTRA: [char; 2] = ['_', '$'];
pub const CONTRACT_QUOTES: [char; 2] = ['\'', '"'];
pub const CONTRACT_OPENERS: [char; 3] = ['(', '[', '{'];
pub const CONTRACT_CLOSERS: [char; 3] = [')', ']', '}'];
/// `ContractAdoptionError`'s message when two contract edits overlap.
pub const CONTRACT_OVERLAP_MESSAGE: &str = "overlapping contract source edits";
pub const SHARED_SCHEMA_CONFLICT: &str = "model uses a shared SCHEMA declaration";
pub const EXTERNAL_SCHEMA_CONFLICT: &str = "effective columns are owned by an external schema file";
pub const MODEL_HEADER_CONFLICT: &str = "MODEL header could not be edited safely";
pub const GENERATED_SOURCE_CONFLICT: &str = "source file is marked as generated";
pub const SOURCE_BLOCK_CONFLICT: &str = "source declaration has no unambiguous YAML block";
/// The `ValueError` prefix of a `name_pattern` the native matcher rejects.
pub const INVALID_NAME_PATTERN_PREFIX: &str = "invalid name_pattern: ";
