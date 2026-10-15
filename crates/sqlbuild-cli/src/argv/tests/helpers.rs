use crate::argv::main::parse_cli_arguments::parse_cli_arguments;
use crate::argv::models::{ArgvOutcome, ArgvSettings, Value};
use crate::argv::tests::test_types::FakeHost;

/// Parse `argv` at the recorded 100-column width without colour.
pub(super) fn parse(argv: &[&str]) -> ArgvOutcome {
    let argv: Vec<String> = argv.iter().map(|arg| (*arg).to_owned()).collect();
    let settings: ArgvSettings = ArgvSettings {
        columns: 100,
        use_color: false,
    };
    parse_cli_arguments(&argv, Vec::new(), settings, &mut FakeHost)
}

/// A list of string values.
pub(super) fn strings(items: &[&str]) -> Value {
    Value::List(
        items
            .iter()
            .map(|item| Value::Str((*item).to_owned()))
            .collect(),
    )
}

/// Owned copies of command-line strings.
pub(super) fn owned(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}
