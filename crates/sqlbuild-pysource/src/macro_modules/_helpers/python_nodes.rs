//! The ruff tree as CPython `ast` nodes in `iter_child_nodes` order, leaf nodes left out.

use ruff_python_ast::{
    Arguments, Comprehension, Decorator, ElifElseClause, ExceptHandler, ExceptHandlerExceptHandler,
    Expr, ExprName, FStringPart, InterpolatedElement, InterpolatedStringElement,
    InterpolatedStringElements, InterpolatedStringFormatSpec, Keyword, MatchCase, ModModule,
    Parameter, Parameters, Pattern, Stmt, TypeParam, TypeParams, WithItem,
};
use std::collections::VecDeque;
use std::iter::once;

/// One CPython `ast` node over the ruff tree.
#[derive(Clone, Copy)]
pub(crate) enum PyNode<'a> {
    Module(&'a ModModule),
    Stmt(&'a Stmt),
    Expr(&'a Expr),
    /// An `If` whose `orelse` CPython nests from ruff's `elif`/`else` clauses.
    IfChain(&'a Expr, &'a [Stmt], &'a [ElifElseClause]),
    Arguments(&'a Parameters),
    Arg(&'a Parameter),
    Keyword(&'a Keyword),
    Comprehension(&'a Comprehension),
    WithItem(&'a WithItem),
    MatchCase(&'a MatchCase),
    Pattern(&'a Pattern),
    Handler(&'a ExceptHandlerExceptHandler),
    TypeParam(&'a TypeParam),
    /// A `FormattedValue` or `Interpolation`.
    Formatted(&'a InterpolatedElement),
    /// The `JoinedStr` of a format spec.
    FormatSpec(&'a InterpolatedStringFormatSpec),
}

impl<'a> PyNode<'a> {
    /// The `ExprName` this node is, if it is a `Name`.
    pub(crate) fn name(self) -> Option<&'a ExprName> {
        match self {
            Self::Expr(Expr::Name(name)) => Some(name),
            _ => None,
        }
    }

    /// Whether a depth-first walk of runtime nodes stops here: nested functions, lambdas, classes.
    pub(crate) fn opens_scope(self) -> bool {
        matches!(
            self,
            Self::Stmt(Stmt::FunctionDef(_) | Stmt::ClassDef(_)) | Self::Expr(Expr::Lambda(_))
        )
    }

    /// The children `ast.iter_child_nodes` yields, in order, without leaf nodes.
    pub(crate) fn children(self) -> Vec<PyNode<'a>> {
        match self {
            Self::Module(module) => statements(&module.body).collect(),
            Self::Stmt(statement) => statement_children(statement),
            Self::Expr(expression) => expression_children(expression),
            Self::IfChain(test, body, clauses) => if_children((test, body, clauses)),
            Self::Arguments(parameters) => argument_children(parameters),
            Self::Arg(parameter) => optional(parameter.annotation.as_deref()).collect(),
            Self::Keyword(keyword) => vec![Self::Expr(&keyword.value)],
            Self::Comprehension(comprehension) => [
                Self::Expr(&comprehension.target),
                Self::Expr(&comprehension.iter),
            ]
            .into_iter()
            .chain(expressions(&comprehension.ifs))
            .collect(),
            Self::WithItem(item) => once(Self::Expr(&item.context_expr))
                .chain(optional(item.optional_vars.as_deref()))
                .collect(),
            Self::MatchCase(case) => once(Self::Pattern(&case.pattern))
                .chain(optional(case.guard.as_deref()))
                .chain(statements(&case.body))
                .collect(),
            Self::Pattern(pattern) => pattern_children(pattern),
            Self::Handler(handler) => optional(handler.type_.as_deref())
                .chain(statements(&handler.body))
                .collect(),
            Self::TypeParam(parameter) => type_param_children(parameter),
            Self::Formatted(element) => once(Self::Expr(&element.expression))
                .chain(element.format_spec.as_deref().map(Self::FormatSpec))
                .collect(),
            Self::FormatSpec(spec) => interpolations(&spec.elements).collect(),
        }
    }

    /// Every node `ast.walk` yields from this one, in its breadth-first order.
    pub(crate) fn walk(self) -> Vec<PyNode<'a>> {
        let mut found: Vec<PyNode<'a>> = Vec::new();
        let mut pending: VecDeque<PyNode<'a>> = VecDeque::from([self]);
        while let Some(node) = pending.pop_front() {
            pending.extend(node.children());
            found.push(node);
        }
        found
    }
}

fn statements<'a>(body: &'a [Stmt]) -> impl Iterator<Item = PyNode<'a>> {
    body.iter().map(PyNode::Stmt)
}

fn expressions<'a>(values: &'a [Expr]) -> impl Iterator<Item = PyNode<'a>> {
    values.iter().map(PyNode::Expr)
}

fn optional(value: Option<&Expr>) -> impl Iterator<Item = PyNode<'_>> {
    value.into_iter().map(PyNode::Expr)
}

fn type_params(parameters: Option<&TypeParams>) -> impl Iterator<Item = PyNode<'_>> {
    parameters
        .into_iter()
        .flat_map(|parameters| parameters.type_params.iter().map(PyNode::TypeParam))
}

fn decorators(decorators: &[Decorator]) -> impl Iterator<Item = PyNode<'_>> {
    decorators
        .iter()
        .map(|decorator| PyNode::Expr(&decorator.expression))
}

fn handlers(handlers: &[ExceptHandler]) -> impl Iterator<Item = PyNode<'_>> {
    handlers
        .iter()
        .map(|ExceptHandler::ExceptHandler(handler)| PyNode::Handler(handler))
}

fn class_bases(arguments: Option<&Arguments>) -> Vec<PyNode<'_>> {
    arguments.map_or_else(Vec::new, |arguments| {
        expressions(&arguments.args)
            .chain(arguments.keywords.iter().map(PyNode::Keyword))
            .collect()
    })
}

fn statement_children(statement: &Stmt) -> Vec<PyNode<'_>> {
    match statement {
        Stmt::FunctionDef(function) => once(PyNode::Arguments(&function.parameters))
            .chain(statements(&function.body))
            .chain(decorators(&function.decorator_list))
            .chain(optional(function.returns.as_deref()))
            .chain(type_params(function.type_params.as_deref()))
            .collect(),
        Stmt::ClassDef(class) => class_bases(class.arguments.as_deref())
            .into_iter()
            .chain(statements(&class.body))
            .chain(decorators(&class.decorator_list))
            .chain(type_params(class.type_params.as_deref()))
            .collect(),
        Stmt::Return(statement) => optional(statement.value.as_deref()).collect(),
        Stmt::Delete(statement) => expressions(&statement.targets).collect(),
        Stmt::TypeAlias(statement) => once(PyNode::Expr(&statement.name))
            .chain(type_params(statement.type_params.as_deref()))
            .chain(once(PyNode::Expr(&statement.value)))
            .collect(),
        Stmt::Assign(statement) => expressions(&statement.targets)
            .chain(once(PyNode::Expr(&statement.value)))
            .collect(),
        Stmt::AugAssign(statement) => vec![
            PyNode::Expr(&statement.target),
            PyNode::Expr(&statement.value),
        ],
        Stmt::AnnAssign(statement) => [
            PyNode::Expr(&statement.target),
            PyNode::Expr(&statement.annotation),
        ]
        .into_iter()
        .chain(optional(statement.value.as_deref()))
        .collect(),
        Stmt::For(statement) => [
            PyNode::Expr(&statement.target),
            PyNode::Expr(&statement.iter),
        ]
        .into_iter()
        .chain(statements(&statement.body))
        .chain(statements(&statement.orelse))
        .collect(),
        Stmt::While(statement) => once(PyNode::Expr(&statement.test))
            .chain(statements(&statement.body))
            .chain(statements(&statement.orelse))
            .collect(),
        Stmt::If(statement) => if_children((
            &statement.test,
            &statement.body,
            &statement.elif_else_clauses,
        )),
        Stmt::With(statement) => statement
            .items
            .iter()
            .map(PyNode::WithItem)
            .chain(statements(&statement.body))
            .collect(),
        Stmt::Match(statement) => once(PyNode::Expr(&statement.subject))
            .chain(statement.cases.iter().map(PyNode::MatchCase))
            .collect(),
        Stmt::Raise(statement) => optional(statement.exc.as_deref())
            .chain(optional(statement.cause.as_deref()))
            .collect(),
        Stmt::Try(statement) => statements(&statement.body)
            .chain(handlers(&statement.handlers))
            .chain(statements(&statement.orelse))
            .chain(statements(&statement.finalbody))
            .collect(),
        Stmt::Assert(statement) => once(PyNode::Expr(&statement.test))
            .chain(optional(statement.msg.as_deref()))
            .collect(),
        Stmt::Expr(statement) => vec![PyNode::Expr(&statement.value)],
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

/// An `If`'s test and body, then its `orelse`: the next `elif` as a nested `If`, or `else` body.
fn if_children<'a>(
    (test, body, clauses): (&'a Expr, &'a [Stmt], &'a [ElifElseClause]),
) -> Vec<PyNode<'a>> {
    let orelse: Vec<PyNode<'a>> = clauses
        .split_first()
        .map_or_else(Vec::new, |(clause, rest)| match &clause.test {
            Some(elif_test) => vec![PyNode::IfChain(elif_test, &clause.body, rest)],
            None => statements(&clause.body).collect(),
        });
    once(PyNode::Expr(test))
        .chain(statements(body))
        .chain(orelse)
        .collect()
}

/// `posonlyargs, args, vararg, kwonlyargs, kw_defaults, kwarg, defaults`.
fn argument_children(parameters: &Parameters) -> Vec<PyNode<'_>> {
    let positional = || parameters.posonlyargs.iter().chain(&parameters.args);
    positional()
        .map(|parameter| PyNode::Arg(&parameter.parameter))
        .chain(parameters.vararg.as_deref().map(PyNode::Arg))
        .chain(
            parameters
                .kwonlyargs
                .iter()
                .map(|parameter| PyNode::Arg(&parameter.parameter)),
        )
        .chain(
            parameters
                .kwonlyargs
                .iter()
                .filter_map(|parameter| parameter.default.as_deref().map(PyNode::Expr)),
        )
        .chain(parameters.kwarg.as_deref().map(PyNode::Arg))
        .chain(positional().filter_map(|parameter| parameter.default.as_deref().map(PyNode::Expr)))
        .collect()
}

fn interpolations(elements: &InterpolatedStringElements) -> impl Iterator<Item = PyNode<'_>> {
    elements.iter().filter_map(|element| match element {
        InterpolatedStringElement::Interpolation(interpolation) => {
            Some(PyNode::Formatted(interpolation))
        }
        InterpolatedStringElement::Literal(_) => None,
    })
}

fn fstring_parts(part: &FStringPart) -> Vec<PyNode<'_>> {
    match part {
        FStringPart::FString(fstring) => interpolations(&fstring.elements).collect(),
        FStringPart::Literal(_) => Vec::new(),
    }
}

fn comprehension_children<'a>(
    leading: Vec<PyNode<'a>>,
    generators: &'a [Comprehension],
) -> Vec<PyNode<'a>> {
    leading
        .into_iter()
        .chain(generators.iter().map(PyNode::Comprehension))
        .collect()
}

fn expression_children(expression: &Expr) -> Vec<PyNode<'_>> {
    match expression {
        Expr::BoolOp(node) => expressions(&node.values).collect(),
        Expr::Named(node) => vec![PyNode::Expr(&node.target), PyNode::Expr(&node.value)],
        Expr::BinOp(node) => vec![PyNode::Expr(&node.left), PyNode::Expr(&node.right)],
        Expr::UnaryOp(node) => vec![PyNode::Expr(&node.operand)],
        Expr::Lambda(node) => node
            .parameters
            .as_deref()
            .map(PyNode::Arguments)
            .into_iter()
            .chain(once(PyNode::Expr(&node.body)))
            .collect(),
        Expr::If(node) => vec![
            PyNode::Expr(&node.test),
            PyNode::Expr(&node.body),
            PyNode::Expr(&node.orelse),
        ],
        Expr::Dict(node) => node
            .items
            .iter()
            .filter_map(|item| item.key.as_ref().map(PyNode::Expr))
            .chain(node.items.iter().map(|item| PyNode::Expr(&item.value)))
            .collect(),
        Expr::Set(node) => expressions(&node.elts).collect(),
        Expr::ListComp(node) => {
            comprehension_children(vec![PyNode::Expr(&node.elt)], &node.generators)
        }
        Expr::SetComp(node) => {
            comprehension_children(vec![PyNode::Expr(&node.elt)], &node.generators)
        }
        Expr::DictComp(node) => comprehension_children(
            optional(node.key.as_deref())
                .chain(once(PyNode::Expr(&node.value)))
                .collect(),
            &node.generators,
        ),
        Expr::Generator(node) => {
            comprehension_children(vec![PyNode::Expr(&node.elt)], &node.generators)
        }
        Expr::Await(node) => vec![PyNode::Expr(&node.value)],
        Expr::Yield(node) => optional(node.value.as_deref()).collect(),
        Expr::YieldFrom(node) => vec![PyNode::Expr(&node.value)],
        Expr::Compare(node) => once(PyNode::Expr(&node.left))
            .chain(expressions(&node.comparators))
            .collect(),
        Expr::Call(node) => once(PyNode::Expr(&node.func))
            .chain(expressions(&node.arguments.args))
            .chain(node.arguments.keywords.iter().map(PyNode::Keyword))
            .collect(),
        Expr::FString(node) => node.value.iter().flat_map(fstring_parts).collect(),
        Expr::TString(node) => node
            .value
            .iter()
            .flat_map(|tstring| interpolations(&tstring.elements))
            .collect(),
        Expr::Attribute(node) => vec![PyNode::Expr(&node.value)],
        Expr::Subscript(node) => vec![PyNode::Expr(&node.value), PyNode::Expr(&node.slice)],
        Expr::Starred(node) => vec![PyNode::Expr(&node.value)],
        Expr::List(node) => expressions(&node.elts).collect(),
        Expr::Tuple(node) => expressions(&node.elts).collect(),
        Expr::Slice(node) => optional(node.lower.as_deref())
            .chain(optional(node.upper.as_deref()))
            .chain(optional(node.step.as_deref()))
            .collect(),
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

fn pattern_children(pattern: &Pattern) -> Vec<PyNode<'_>> {
    match pattern {
        Pattern::MatchValue(node) => vec![PyNode::Expr(&node.value)],
        Pattern::MatchSequence(node) => node.patterns.iter().map(PyNode::Pattern).collect(),
        Pattern::MatchMapping(node) => expressions(&node.keys)
            .chain(node.patterns.iter().map(PyNode::Pattern))
            .collect(),
        Pattern::MatchClass(node) => once(PyNode::Expr(&node.cls))
            .chain(node.arguments.patterns.iter().map(PyNode::Pattern))
            .chain(
                node.arguments
                    .keywords
                    .iter()
                    .map(|keyword| PyNode::Pattern(&keyword.pattern)),
            )
            .collect(),
        Pattern::MatchAs(node) => node
            .pattern
            .as_deref()
            .map(PyNode::Pattern)
            .into_iter()
            .collect(),
        Pattern::MatchOr(node) => node.patterns.iter().map(PyNode::Pattern).collect(),
        Pattern::MatchSingleton(_) | Pattern::MatchStar(_) => Vec::new(),
    }
}

fn type_param_children(parameter: &TypeParam) -> Vec<PyNode<'_>> {
    match parameter {
        TypeParam::TypeVar(node) => optional(node.bound.as_deref())
            .chain(optional(node.default.as_deref()))
            .collect(),
        TypeParam::TypeVarTuple(node) => optional(node.default.as_deref()).collect(),
        TypeParam::ParamSpec(node) => optional(node.default.as_deref()).collect(),
    }
}
