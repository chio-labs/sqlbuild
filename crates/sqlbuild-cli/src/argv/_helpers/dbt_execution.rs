//! The plain host and namespace reading of the `sqb dbt` execution parser.

use sqlbuild_core::dbt_cli::models::DbtParsedFlags;
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::argv::models::{Namespace, TypeFailure, Value};
use crate::argv::types::ArgvHost;

/// The execution parser declares no converters and no version.
pub(crate) struct PlainHost;

impl ArgvHost for PlainHost {
    fn convert(&mut self, _converter: &str, text: &str) -> Result<Value, TypeFailure> {
        Ok(Value::Str(text.to_owned()))
    }

    fn repr(&self, text: &str) -> String {
        python_str_repr(text)
    }

    fn program_version(&mut self) -> String {
        String::new()
    }
}

fn texts(namespace: &Namespace, name: &str) -> Vec<String> {
    match namespace.value(name) {
        Value::List(items) => items.into_iter().filter_map(string).collect(),
        _ => Vec::new(),
    }
}

fn text(namespace: &Namespace, name: &str) -> Option<String> {
    string(namespace.value(name))
}

fn string(value: Value) -> Option<String> {
    match value {
        Value::Str(text) => Some(text),
        _ => None,
    }
}

fn flag(namespace: &Namespace, name: &str) -> bool {
    namespace.value(name) == Value::Bool(true)
}

/// The parsed flags, the strings after `--` appended to the passthrough positional.
pub(crate) fn parsed_flags(namespace: &Namespace, tail: Vec<String>) -> DbtParsedFlags {
    let mut dbt_passthrough: Vec<String> = texts(namespace, "dbt_passthrough");
    dbt_passthrough.extend(tail);
    DbtParsedFlags {
        select: texts(namespace, "select"),
        exclude: texts(namespace, "exclude"),
        vars: text(namespace, "vars"),
        threads: text(namespace, "threads"),
        full_refresh: flag(namespace, "full_refresh"),
        event_time_start: text(namespace, "event_time_start"),
        event_time_end: text(namespace, "event_time_end"),
        project_dir: text(namespace, "project_dir"),
        profiles_dir: text(namespace, "profiles_dir"),
        profile: text(namespace, "profile"),
        target: text(namespace, "target"),
        target_path: text(namespace, "target_path"),
        state: text(namespace, "state"),
        indirect_selection: text(namespace, "indirect_selection"),
        defer: flag(namespace, "defer"),
        start_cursor_ts: text(namespace, "start_cursor_ts"),
        end_cursor_ts: text(namespace, "end_cursor_ts"),
        start_cursor_int: text(namespace, "start_cursor_int"),
        end_cursor_int: text(namespace, "end_cursor_int"),
        defer_to: text(namespace, "defer_to"),
        fail_fast: flag(namespace, "fail_fast"),
        hard_copy: flag(namespace, "hard_copy"),
        dbt_passthrough,
    }
}
