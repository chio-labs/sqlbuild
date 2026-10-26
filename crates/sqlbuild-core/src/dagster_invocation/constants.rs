//! Dagster invocation flags and limits.

/// The flag that writes the execution JSON document to a path.
pub const JSON_OUTPUT_FLAG: &str = "--json-output";
/// Flags that already request JSON output.
pub const JSON_OUTPUT_FLAGS: [&str; 2] = ["--json", "--json-output"];
/// Scenario test flags that take a value.
pub const SCENARIO_VALUE_FLAGS: [&str; 4] = [
    "--max-snapshot-rows",
    "--max-snapshot-total-rows",
    "--max-snapshot-bytes",
    "--max-snapshot-total-bytes",
];
/// Arguments of `scenario test` before its selectors.
pub const SCENARIO_TEST_ARGUMENT_COUNT: usize = 2;
/// Separator replacing characters a Dagster check name cannot hold.
pub const CHECK_NAME_SEPARATOR: char = '_';
/// Check name used when nothing printable remains.
pub const DEFAULT_CHECK_NAME: &str = "check";
/// Characters of process output kept in failure diagnostics.
pub const MAX_DIAGNOSTIC_CHARS: usize = 4_000;
/// Indentation of SQL in failure text.
pub const SQL_INDENT: &str = "    ";
/// Separator replacing characters a Dagster tag key or name segment cannot hold.
pub const NAME_SEPARATOR: char = '_';
/// ASCII punctuation a Dagster tag key keeps besides letters, digits and `_`.
pub const TAG_KEY_PUNCTUATION: [char; 3] = ['.', '-', '/'];
/// The Markdown code-span delimiter.
pub const CODE_SPAN_MARK: char = '`';
/// Edge characters that need padding inside a Markdown code span.
pub(crate) const CODE_SPAN_PADDED_EDGES: [char; 2] = [CODE_SPAN_MARK, ' '];
/// The default translator's description kind of a node without one.
pub const DEFAULT_ASSET_KIND: &str = "asset";
/// The default translator's description name of a node without one.
pub const DEFAULT_ASSET_NAME: &str = "unknown";
/// Failed checks and models a failure description names before "and N more".
pub const MAX_SUMMARIZED_FAILURES: usize = 10;
