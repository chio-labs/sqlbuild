//! CPython `ast` nodes mirrored over the ruff tree, and the line starts of a source.

use ruff_python_ast::{
    Comprehension, ElifElseClause, ExceptHandler, Expr, ExprName, InterpolatedElement,
    InterpolatedStringFormatSpec, Keyword, MatchCase, ModModule, Parameter, Parameters, Pattern,
    Stmt, TypeParam, WithItem,
};
use ruff_text_size::TextSize;

/// One node of the tree CPython's `ast.parse` builds, borrowed from the ruff node it mirrors.
#[derive(Clone, Debug)]
pub(crate) enum CpythonNode<'a> {
    Stmt(&'a Stmt),
    /// The `If` an `elif` clause becomes; the clauses after it form its `orelse`.
    Elif(&'a [ElifElseClause]),
    Expr(&'a Expr),
    Arguments(&'a Parameters),
    Arg(&'a Parameter),
    Keyword(&'a Keyword),
    WithItem(&'a WithItem),
    MatchCase(&'a MatchCase),
    Pattern(&'a Pattern),
    Comprehension(&'a Comprehension),
    ExceptHandler(&'a ExceptHandler),
    TypeParam(&'a TypeParam),
    /// A string `Constant` of an f-string, t-string or format spec, merged as CPython merges it.
    Text(TextConstant),
    /// A `FormattedValue` or `Interpolation`.
    Interpolation(&'a InterpolatedElement),
    /// The `JoinedStr` of a format spec.
    FormatSpec(&'a InterpolatedStringFormatSpec),
}

impl<'a> CpythonNode<'a> {
    /// The `ExprName` this node is, if it is a `Name`.
    pub(crate) fn name(&self) -> Option<&'a ExprName> {
        match self {
            Self::Expr(Expr::Name(name)) => Some(name),
            _ => None,
        }
    }

    /// Whether a depth-first walk of runtime nodes stops here: nested functions, lambdas, classes.
    pub(crate) fn opens_scope(&self) -> bool {
        matches!(
            self,
            Self::Stmt(Stmt::FunctionDef(_) | Stmt::ClassDef(_)) | Self::Expr(Expr::Lambda(_))
        )
    }
}

/// A merged string constant and the offset CPython locates it at.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct TextConstant {
    pub(crate) value: String,
    pub(crate) start: TextSize,
}

/// A module CPython accepts, parsed from its source with newlines translated as CPython does.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ParsedSource {
    pub(crate) module: ModModule,
    pub(crate) lines: SourceLines,
}

/// The byte offsets where the lines of one newline-translated source start.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SourceLines {
    pub(crate) starts: Vec<usize>,
}
