use std::collections::HashMap;
use std::sync::Arc;

use sqlbuild_render::macro_arguments::models::ArgumentValue;

use crate::sql_macros::models::SqlMacroDefinition;

pub(super) struct ExpansionTestCase {
    pub(super) description: &'static str,
    pub(super) adapter: &'static str,
    pub(super) macros: &'static [(&'static str, &'static str)],
    pub(super) sql: &'static str,
    pub(super) expected_sql: &'static str,
}

pub(super) struct ExpansionErrorTestCase {
    pub(super) description: &'static str,
    pub(super) adapter: &'static str,
    pub(super) macros: &'static [(&'static str, &'static str)],
    pub(super) sql: &'static str,
    pub(super) expected_code: &'static str,
    pub(super) expected_message: &'static str,
}

pub(super) struct DefinitionErrorTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_code: &'static str,
    pub(super) expected_message: &'static str,
}

pub(super) struct DefinitionTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_labels: &'static [&'static str],
    pub(super) expected_form: &'static str,
    pub(super) expected_body_position: (usize, usize),
}

pub(super) struct CycleTestCase {
    pub(super) description: &'static str,
    pub(super) calls: &'static [(&'static str, &'static [&'static str])],
    pub(super) expected_cycle: Option<&'static [&'static str]>,
}

/// A host serving parsed macros and fixed declaration values, for one adapter.
pub(super) struct FakeHost {
    pub(super) definitions: HashMap<String, Arc<SqlMacroDefinition>>,
    pub(super) adapter: &'static str,
}

/// A model calling a Python macro with a SQL macro call among its arguments.
pub(super) struct PythonArgumentTestCase {
    pub(super) description: &'static str,
    pub(super) body: &'static str,
    pub(super) sql: &'static str,
    /// What a Python macro receives after the direct expansion: a line break after a `--` comment.
    pub(super) expected_suffix: &'static str,
    /// The argument values, given the SQL macro call's own expansion.
    pub(super) expected_arguments: fn(String) -> Vec<ArgumentValue>,
}

/// Argument parsing without Unicode name lookups, which these arguments never use.
pub(super) struct AsciiArguments;

/// One recorded call, one analysed select item and the type the item then has, if changed.
pub(super) struct OutputTypeTestCase {
    pub(super) description: &'static str,
    pub(super) check: crate::sql_macros::models::SqlMacroCheck,
    /// The item's CTE (`None` for the main query), set-operation branch, name and inferred type.
    pub(super) item: (
        Option<&'static str>,
        usize,
        &'static str,
        Option<&'static str>,
    ),
    pub(super) expected_type: Option<&'static str>,
}

/// Model SQL and the scope and alias of each whole-item SQL macro call.
pub(super) struct OutputNamesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_names: &'static [(Option<&'static str>, usize, &'static str)],
}

pub(super) struct MacroDescriptionTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_description: &'static str,
}

pub(super) struct MacroQuoteErrorTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_message: &'static str,
    pub(super) expected_location: (usize, usize),
}
