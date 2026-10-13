//! The `@udf(...)` decorator, its imports and the function docstring, read from the ruff tree.

use ruff_python_ast::{Decorator, Expr, ExprCall, Identifier, Keyword, Stmt, StmtFunctionDef};
use ruff_text_size::Ranged;

use crate::cpython_tree::main::source_position::source_position;
use crate::cpython_tree::models::SourceLines;
use crate::udf_functions::_helpers::docstrings::clean_docstring;
use crate::udf_functions::constants::{UDF_DECORATOR_NAME, UDF_IMPORT_MODULES};
use crate::udf_functions::models::UdfKeyword;

/// The decorator's call when it is `udf(...)` or `<anything>.udf(...)`.
pub(crate) fn udf_call(decorator: &Decorator) -> Option<&ExprCall> {
    let Expr::Call(call) = &decorator.expression else {
        return None;
    };
    let name: &str = match call.func.as_ref() {
        Expr::Name(name) => name.id.as_str(),
        Expr::Attribute(attribute) => attribute.attr.as_str(),
        _ => return None,
    };
    (name == UDF_DECORATOR_NAME).then_some(call)
}

/// `from sqlbuild import udf` or `from sqlbuild.functions import udf`, at any relative level.
pub(crate) fn is_udf_import(statement: &Stmt) -> bool {
    let Stmt::ImportFrom(import) = statement else {
        return false;
    };
    import
        .module
        .as_ref()
        .is_some_and(|module| UDF_IMPORT_MODULES.contains(&module.as_str()))
        && import
            .names
            .iter()
            .any(|alias| alias.name.as_str() == UDF_DECORATOR_NAME)
}

/// `ast.get_docstring(function)`: a leading string expression statement, cleaned.
pub(crate) fn docstring(function: &StmtFunctionDef) -> Option<String> {
    let Some(Stmt::Expr(statement)) = function.body.first() else {
        return None;
    };
    let Expr::StringLiteral(literal) = statement.value.as_ref() else {
        return None;
    };
    Some(clean_docstring(literal.value.to_str()))
}

/// One `@udf(...)` keyword: its name, or `None` for `**mapping`, and the line it starts on.
pub(crate) fn udf_keyword(keyword: &Keyword, lines: &SourceLines) -> UdfKeyword {
    UdfKeyword {
        name: keyword.arg.as_ref().map(Identifier::to_string),
        line: source_position(lines, keyword.range().start()).0,
    }
}
