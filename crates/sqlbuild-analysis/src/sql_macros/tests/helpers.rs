use std::sync::Arc;

use crate::sql_macros::_helpers::expansion::expand_text;
use crate::sql_macros::errors::ExpansionFailure;
use crate::sql_macros::errors::SqlMacroError;
use crate::sql_macros::main::parse_sql_macro::parse_sql_macro;
use crate::sql_macros::models::{
    CallScope, SqlMacroCheck, SqlMacroDefinition, TextContext, TypedOutput,
};
use crate::sql_macros::tests::test_types::{AsciiArguments, FakeHost};
use crate::sql_macros::types::{ConstantShape, SqlMacroHost, SqlMacroScope};

/// Constants and enum members the fake host renders, by reference text.
const DECLARATIONS: [(&str, &str); 4] = [
    ("@const(\"supported_countries\")", "('GB', 'FR', 'HK')"),
    ("@const(\"price_places\")", "2"),
    ("@enum(\"order_status\").CLOSED", "'closed'"),
    ("@enum(\"order_status\").OPEN", "'open'"),
];

impl FakeHost {
    pub(super) fn new(macros: &[(&str, &str)], adapter: &'static str) -> Self {
        let definitions = macros
            .iter()
            .map(|(name, source)| {
                let path: String = format!("macros/sql/{name}.sql");
                let definition = parse_sql_macro(name, &path, source).expect("valid macro");
                ((*name).to_owned(), Arc::new(definition))
            })
            .collect();
        Self {
            definitions,
            adapter,
        }
    }
}

impl SqlMacroHost for FakeHost {
    type Error = String;

    fn definition(
        &self,
        _scope: &SqlMacroScope,
        name: &str,
    ) -> Result<Arc<SqlMacroDefinition>, ExpansionFailure<String>> {
        self.definitions
            .get(name)
            .cloned()
            .ok_or_else(|| ExpansionFailure::Host(format!("unknown macro {name}")))
    }

    fn render_declarations(
        &self,
        _scope: &SqlMacroScope,
        text: &str,
    ) -> Result<String, ExpansionFailure<String>> {
        let mut rendered: String = text.to_owned();
        for (reference, value) in DECLARATIONS {
            rendered = rendered.replace(reference, value);
        }
        Ok(rendered)
    }

    fn constant_shape(
        &self,
        _scope: &SqlMacroScope,
        name: &str,
    ) -> Result<ConstantShape, ExpansionFailure<String>> {
        Ok(if name == "supported_countries" {
            ConstantShape::Collection
        } else {
            ConstantShape::Scalar
        })
    }

    fn render_collection(&self, text: &str) -> Result<String, ExpansionFailure<String>> {
        let inner: &str = text
            .trim()
            .trim_start_matches(['[', '{'])
            .trim_end_matches([']', '}']);
        let items: Vec<String> = inner
            .split(',')
            .map(|item| format!("'{}'", item.trim().trim_matches('"')))
            .collect();
        Ok(format!("({})", items.join(", ")))
    }

    fn adapter(&self) -> &str {
        self.adapter
    }
}

/// `sql` expanded with `macros` for `adapter`, or the SQL macro error it raised.
pub(super) fn expanded_for(
    adapter: &'static str,
    macros: &[(&str, &str)],
    sql: &str,
) -> Result<String, SqlMacroError> {
    let host: FakeHost = FakeHost::new(macros, adapter);
    let context = TextContext {
        text: sql,
        scope: &SqlMacroScope::Caller,
        stack: &[],
        owner: "model:orders_clean",
    };
    expand_text(&host, &context).map_err(macro_error)
}

/// The SQL macro error of a failed expansion; the fake host itself never fails.
fn macro_error(failure: ExpansionFailure<String>) -> SqlMacroError {
    let ExpansionFailure::Macro(error) = failure else {
        panic!("the fake host failed");
    };
    error
}

/// Each name as an owned string.
pub(super) fn owned(names: &[&str]) -> Vec<String> {
    names.iter().map(|name| (*name).to_owned()).collect()
}

impl sqlbuild_render::macro_arguments::types::ArgumentHost for AsciiArguments {
    fn character_named(&self, _name: &str) -> Option<String> {
        None
    }

    fn identifier(&self, _text: &str) -> Option<String> {
        None
    }
}

/// A check recording output `label` of `shout()`, typed VARCHAR, at `scope`'s `branch`.
pub(super) fn typed_check(scope: CallScope, branch: usize) -> SqlMacroCheck {
    SqlMacroCheck {
        macro_name: "shout".to_owned(),
        scope,
        plain_select: true,
        arguments: Vec::new(),
        call: None,
        output: Some(TypedOutput {
            name: "label".to_owned(),
            returns: "VARCHAR".to_owned(),
            branch,
        }),
    }
}
