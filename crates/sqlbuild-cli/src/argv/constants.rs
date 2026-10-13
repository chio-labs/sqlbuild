//! The `sqb` command table, `argparse` vocabulary and the post-parse rules' names.

/// The exported `sqb` parser tree: every parser, group and action in `add_argument` order.
pub(crate) const COMMAND_TABLE: &str = include_str!("data/commands.json");
/// `argparse.SUPPRESS` as a destination.
pub(crate) const SUPPRESS_DEST: &str = "==SUPPRESS==";
/// The placeholder of the installed version in the `--version` text.
pub(crate) const VERSION_PLACEHOLDER: &str = "{version}";
pub(crate) const PREFIX_CHARS: char = '-';
pub(crate) const OPTIONS_TERMINATOR: &str = "--";
pub(crate) const USAGE_PREFIX: &str = "usage: ";
/// `SqlbuildArgumentParser.error`'s coded prefix and its `CliStyle.error_strong` colours.
pub(crate) const ERROR_PREFIX: &str = "error[C900]:";
pub(crate) const ERROR_STRONG_STYLE: &str = "\u{1b}[38;5;167m\u{1b}[1m";
pub(crate) const STYLE_RESET: &str = "\u{1b}[0m";
pub(crate) const PARSER_ERROR_EXIT: i64 = 2;
pub(crate) const HELP_EXIT: i64 = 0;
pub(crate) const INDENT_INCREMENT: i64 = 2;
pub(crate) const MAX_HELP_POSITION: i64 = 24;
pub(crate) const MINIMUM_TEXT_WIDTH: i64 = 11;
/// `_long_break_matcher` folds longer runs of newlines into this many.
pub(crate) const MAXIMUM_BLANK_RUN: usize = 2;
/// `textwrap`'s em-dash is at least this many hyphens.
pub(crate) const MINIMUM_EM_DASH: usize = 2;

/// `CliNamespace` attributes the post-parse rules read and write.
pub(crate) const COMMAND_DEST: &str = "command";
pub(crate) const DBT_COMMAND: &str = "dbt";
pub(crate) const DBT_DEBUG_COMMAND: &str = "debug";
pub(crate) const DBT_PASSTHROUGH_COMMANDS: [&str; 4] = ["plan", "run", "build", "debug"];
pub(crate) const DBT_PASSTHROUGH_SEPARATOR: &str = "--";
pub(crate) const DBT_VERBOSE_OPTIONS: [&str; 2] = ["--verbose", "-v"];
pub(crate) const DBT_VERBOSE_OPTION: &str = "--verbose";
pub(crate) const NO_COLOR_OPTION: &str = "--no-color";
pub(crate) const DEBUG_OPTION: &str = "--debug";
pub(crate) const POSITIONAL_SELECT_COMMANDS: [&str; 8] = [
    "audit",
    "build",
    "check",
    "compile",
    "freshness",
    "plan",
    "seed",
    "test",
];
pub(crate) const CONCURRENCY_COMMANDS: [&str; 5] = ["audit", "build", "load", "seed", "test"];
pub(crate) const CURSOR_COMMANDS: [&str; 3] = ["build", "load", "plan"];
pub(crate) const SCOPE_COMMAND: &str = "scope";
pub(crate) const TEST_COMMAND: &str = "test";
pub(crate) const JANITOR_COMMAND: &str = "janitor";
pub(crate) const CONCURRENCY_ENV_VAR: &str = "SQLBUILD_CONCURRENCY";
pub(crate) const SCOPE_GLOBAL_SUMMARY: &str = "summary";
pub(crate) const SCOPE_DEFAULT_PAGE_SIZE: i64 = 100;
pub(crate) const SCOPE_KIND_DEST: &str = "scope_kind";
pub(crate) const INT_CONVERTER: &str = "int";
/// The `type=pathlib.Path` converter, which never rejects a string.
pub(crate) const PATH_CONVERTER: &str = "Path";
