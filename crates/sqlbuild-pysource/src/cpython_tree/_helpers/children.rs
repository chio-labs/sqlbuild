//! The children CPython's `ast.iter_child_nodes` yields, in `_fields` order.

use ruff_python_ast::{
    ElifElseClause, ExceptHandler, Expr, Parameters, Pattern, Stmt, Suite, TypeParam, TypeParams,
};

use crate::cpython_tree::_helpers::joined::{element_pieces, merged_values};
use crate::cpython_tree::main::joined_values::joined_values;
use crate::cpython_tree::models::CpythonNode;

/// The child nodes of `node` that can hold other nodes; operator and context leaves are omitted.
pub(crate) fn children<'a>(node: &CpythonNode<'a>) -> Vec<CpythonNode<'a>> {
    match node {
        CpythonNode::Stmt(statement) => statement_children(statement),
        CpythonNode::Elif(clauses) => elif_children(clauses),
        CpythonNode::Expr(expression) => expression_children(expression),
        CpythonNode::Arguments(parameters) => argument_children(parameters),
        CpythonNode::Arg(parameter) => optional(parameter.annotation.as_deref()),
        CpythonNode::Keyword(keyword) => vec![CpythonNode::Expr(&keyword.value)],
        CpythonNode::WithItem(item) => [
            vec![CpythonNode::Expr(&item.context_expr)],
            optional(item.optional_vars.as_deref()),
        ]
        .concat(),
        CpythonNode::MatchCase(case) => [
            vec![CpythonNode::Pattern(&case.pattern)],
            optional(case.guard.as_deref()),
            statements(&case.body),
        ]
        .concat(),
        CpythonNode::Pattern(pattern) => pattern_children(pattern),
        CpythonNode::Comprehension(comprehension) => [
            vec![
                CpythonNode::Expr(&comprehension.target),
                CpythonNode::Expr(&comprehension.iter),
            ],
            expressions(&comprehension.ifs),
        ]
        .concat(),
        CpythonNode::ExceptHandler(ExceptHandler::ExceptHandler(handler)) => [
            optional(handler.type_.as_deref()),
            statements(&handler.body),
        ]
        .concat(),
        CpythonNode::TypeParam(parameter) => type_param_children(parameter),
        CpythonNode::Text(_) => Vec::new(),
        CpythonNode::Interpolation(interpolation) => {
            let spec: Vec<CpythonNode<'a>> = interpolation
                .format_spec
                .iter()
                .map(|spec| CpythonNode::FormatSpec(spec))
                .collect();
            [vec![CpythonNode::Expr(&interpolation.expression)], spec].concat()
        }
        CpythonNode::FormatSpec(spec) => merged_values(element_pieces(&spec.elements)),
    }
}

fn optional(expression: Option<&Expr>) -> Vec<CpythonNode<'_>> {
    expression.map(CpythonNode::Expr).into_iter().collect()
}

fn expressions(expressions: &[Expr]) -> Vec<CpythonNode<'_>> {
    expressions.iter().map(CpythonNode::Expr).collect()
}

fn statements(body: &Suite) -> Vec<CpythonNode<'_>> {
    body.iter().map(CpythonNode::Stmt).collect()
}

fn decorators(decorator_list: &[ruff_python_ast::Decorator]) -> Vec<CpythonNode<'_>> {
    decorator_list
        .iter()
        .map(|decorator| CpythonNode::Expr(&decorator.expression))
        .collect()
}

fn type_params(parameters: Option<&TypeParams>) -> Vec<CpythonNode<'_>> {
    parameters
        .map(|parameters| parameters.iter().map(CpythonNode::TypeParam).collect())
        .unwrap_or_default()
}

fn statement_children(statement: &Stmt) -> Vec<CpythonNode<'_>> {
    match statement {
        Stmt::FunctionDef(function) => [
            vec![CpythonNode::Arguments(&function.parameters)],
            statements(&function.body),
            decorators(&function.decorator_list),
            optional(function.returns.as_deref()),
            type_params(function.type_params.as_deref()),
        ]
        .concat(),
        Stmt::ClassDef(class) => [
            expressions(class.bases()),
            class.keywords().iter().map(CpythonNode::Keyword).collect(),
            statements(&class.body),
            decorators(&class.decorator_list),
            type_params(class.type_params.as_deref()),
        ]
        .concat(),
        Stmt::Return(statement) => optional(statement.value.as_deref()),
        Stmt::Delete(statement) => expressions(&statement.targets),
        Stmt::TypeAlias(statement) => [
            vec![CpythonNode::Expr(&statement.name)],
            type_params(statement.type_params.as_deref()),
            vec![CpythonNode::Expr(&statement.value)],
        ]
        .concat(),
        Stmt::Assign(statement) => [
            expressions(&statement.targets),
            vec![CpythonNode::Expr(&statement.value)],
        ]
        .concat(),
        Stmt::AugAssign(statement) => vec![
            CpythonNode::Expr(&statement.target),
            CpythonNode::Expr(&statement.value),
        ],
        Stmt::AnnAssign(statement) => [
            vec![
                CpythonNode::Expr(&statement.target),
                CpythonNode::Expr(&statement.annotation),
            ],
            optional(statement.value.as_deref()),
        ]
        .concat(),
        Stmt::For(statement) => [
            vec![
                CpythonNode::Expr(&statement.target),
                CpythonNode::Expr(&statement.iter),
            ],
            statements(&statement.body),
            statements(&statement.orelse),
        ]
        .concat(),
        Stmt::While(statement) => [
            vec![CpythonNode::Expr(&statement.test)],
            statements(&statement.body),
            statements(&statement.orelse),
        ]
        .concat(),
        Stmt::If(statement) => [
            vec![CpythonNode::Expr(&statement.test)],
            statements(&statement.body),
            else_children(&statement.elif_else_clauses),
        ]
        .concat(),
        Stmt::With(statement) => [
            statement.items.iter().map(CpythonNode::WithItem).collect(),
            statements(&statement.body),
        ]
        .concat(),
        Stmt::Match(statement) => [
            vec![CpythonNode::Expr(&statement.subject)],
            statement.cases.iter().map(CpythonNode::MatchCase).collect(),
        ]
        .concat(),
        Stmt::Raise(statement) => [
            optional(statement.exc.as_deref()),
            optional(statement.cause.as_deref()),
        ]
        .concat(),
        Stmt::Try(statement) => [
            statements(&statement.body),
            statement
                .handlers
                .iter()
                .map(CpythonNode::ExceptHandler)
                .collect(),
            statements(&statement.orelse),
            statements(&statement.finalbody),
        ]
        .concat(),
        Stmt::Assert(statement) => [
            vec![CpythonNode::Expr(&statement.test)],
            optional(statement.msg.as_deref()),
        ]
        .concat(),
        Stmt::Expr(statement) => vec![CpythonNode::Expr(&statement.value)],
        Stmt::Import(_)
        | Stmt::ImportFrom(_)
        | Stmt::Global(_)
        | Stmt::Nonlocal(_)
        | Stmt::Pass(_)
        | Stmt::Break(_)
        | Stmt::Continue(_)
        | Stmt::IpyEscapeCommand(_) => Vec::new(),
    }
}

/// The `orelse` of an `If`: a nested `If` for an `elif`, or the `else` body.
fn else_children(clauses: &[ElifElseClause]) -> Vec<CpythonNode<'_>> {
    match clauses.first() {
        Some(clause) if clause.test.is_some() => vec![CpythonNode::Elif(clauses)],
        Some(clause) => statements(&clause.body),
        None => Vec::new(),
    }
}

fn elif_children(clauses: &[ElifElseClause]) -> Vec<CpythonNode<'_>> {
    clauses
        .split_first()
        .map(|(clause, rest)| {
            [
                optional(clause.test.as_ref()),
                statements(&clause.body),
                else_children(rest),
            ]
            .concat()
        })
        .unwrap_or_default()
}

fn expression_children(expression: &Expr) -> Vec<CpythonNode<'_>> {
    match expression {
        Expr::BoolOp(node) => expressions(&node.values),
        Expr::Named(node) => vec![
            CpythonNode::Expr(&node.target),
            CpythonNode::Expr(&node.value),
        ],
        Expr::BinOp(node) => vec![
            CpythonNode::Expr(&node.left),
            CpythonNode::Expr(&node.right),
        ],
        Expr::UnaryOp(node) => vec![CpythonNode::Expr(&node.operand)],
        Expr::Lambda(node) => [
            node.parameters
                .iter()
                .map(|parameters| CpythonNode::Arguments(parameters))
                .collect(),
            vec![CpythonNode::Expr(&node.body)],
        ]
        .concat(),
        Expr::If(node) => vec![
            CpythonNode::Expr(&node.test),
            CpythonNode::Expr(&node.body),
            CpythonNode::Expr(&node.orelse),
        ],
        Expr::Dict(node) => node
            .iter_keys()
            .flatten()
            .chain(node.iter_values())
            .map(CpythonNode::Expr)
            .collect(),
        Expr::Set(node) => expressions(&node.elts),
        Expr::ListComp(node) => comprehension_children(&node.elt, &node.generators),
        Expr::SetComp(node) => comprehension_children(&node.elt, &node.generators),
        Expr::Generator(node) => comprehension_children(&node.elt, &node.generators),
        Expr::DictComp(node) => [
            optional(node.key.as_deref()),
            comprehension_children(&node.value, &node.generators),
        ]
        .concat(),
        Expr::Await(node) => vec![CpythonNode::Expr(&node.value)],
        Expr::Yield(node) => optional(node.value.as_deref()),
        Expr::YieldFrom(node) => vec![CpythonNode::Expr(&node.value)],
        Expr::Compare(node) => [
            vec![CpythonNode::Expr(&node.left)],
            expressions(&node.comparators),
        ]
        .concat(),
        Expr::Call(node) => [
            vec![CpythonNode::Expr(&node.func)],
            expressions(&node.arguments.args),
            node.arguments
                .keywords
                .iter()
                .map(CpythonNode::Keyword)
                .collect(),
        ]
        .concat(),
        Expr::FString(_) | Expr::TString(_) => joined_values(expression),
        Expr::Attribute(node) => vec![CpythonNode::Expr(&node.value)],
        Expr::Subscript(node) => vec![
            CpythonNode::Expr(&node.value),
            CpythonNode::Expr(&node.slice),
        ],
        Expr::Starred(node) => vec![CpythonNode::Expr(&node.value)],
        Expr::List(node) => expressions(&node.elts),
        Expr::Tuple(node) => expressions(&node.elts),
        Expr::Slice(node) => [
            optional(node.lower.as_deref()),
            optional(node.upper.as_deref()),
            optional(node.step.as_deref()),
        ]
        .concat(),
        Expr::StringLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::NumberLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_)
        | Expr::EllipsisLiteral(_)
        | Expr::Name(_)
        | Expr::IpyEscapeCommand(_) => Vec::new(),
    }
}

fn comprehension_children<'a>(
    element: &'a Expr,
    generators: &'a [ruff_python_ast::Comprehension],
) -> Vec<CpythonNode<'a>> {
    [
        vec![CpythonNode::Expr(element)],
        generators.iter().map(CpythonNode::Comprehension).collect(),
    ]
    .concat()
}

/// `arguments` fields: posonlyargs, args, vararg, kwonlyargs, kw_defaults, kwarg, defaults.
fn argument_children(parameters: &Parameters) -> Vec<CpythonNode<'_>> {
    let positional = || parameters.posonlyargs.iter().chain(parameters.args.iter());
    [
        positional()
            .map(|parameter| CpythonNode::Arg(&parameter.parameter))
            .collect(),
        parameters
            .vararg
            .iter()
            .map(|parameter| CpythonNode::Arg(parameter))
            .collect(),
        parameters
            .kwonlyargs
            .iter()
            .map(|parameter| CpythonNode::Arg(&parameter.parameter))
            .collect(),
        parameters
            .kwonlyargs
            .iter()
            .filter_map(|parameter| parameter.default.as_deref())
            .map(CpythonNode::Expr)
            .collect(),
        parameters
            .kwarg
            .iter()
            .map(|parameter| CpythonNode::Arg(parameter))
            .collect(),
        positional()
            .filter_map(|parameter| parameter.default.as_deref())
            .map(CpythonNode::Expr)
            .collect::<Vec<CpythonNode<'_>>>(),
    ]
    .concat()
}

fn pattern_children(pattern: &Pattern) -> Vec<CpythonNode<'_>> {
    match pattern {
        Pattern::MatchValue(node) => vec![CpythonNode::Expr(&node.value)],
        Pattern::MatchSequence(node) => node.patterns.iter().map(CpythonNode::Pattern).collect(),
        Pattern::MatchMapping(node) => [
            expressions(&node.keys),
            node.patterns.iter().map(CpythonNode::Pattern).collect(),
        ]
        .concat(),
        Pattern::MatchClass(node) => [
            vec![CpythonNode::Expr(&node.cls)],
            node.arguments
                .patterns
                .iter()
                .map(CpythonNode::Pattern)
                .collect(),
            node.arguments
                .keywords
                .iter()
                .map(|keyword| CpythonNode::Pattern(&keyword.pattern))
                .collect(),
        ]
        .concat(),
        Pattern::MatchAs(node) => node
            .pattern
            .iter()
            .map(|inner| CpythonNode::Pattern(inner))
            .collect(),
        Pattern::MatchOr(node) => node.patterns.iter().map(CpythonNode::Pattern).collect(),
        Pattern::MatchSingleton(_) | Pattern::MatchStar(_) => Vec::new(),
    }
}

fn type_param_children(parameter: &TypeParam) -> Vec<CpythonNode<'_>> {
    match parameter {
        TypeParam::TypeVar(node) => [
            optional(node.bound.as_deref()),
            optional(node.default.as_deref()),
        ]
        .concat(),
        TypeParam::ParamSpec(node) => optional(node.default.as_deref()),
        TypeParam::TypeVarTuple(node) => optional(node.default.as_deref()),
    }
}
