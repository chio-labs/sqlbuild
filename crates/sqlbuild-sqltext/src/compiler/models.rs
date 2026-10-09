#[derive(Clone, Debug, PartialEq)]
pub enum AuthoredValue {
    Null,
    Boolean(bool),
    BareWord(String),
    String(String),
    List(Vec<AuthoredValue>),
    Map(Vec<(String, AuthoredValue)>),
    Set(Vec<AuthoredValue>),
    Tuple(Vec<AuthoredValue>),
    TypedConstant(Vec<(String, AuthoredValue)>),
    InlineSqlHook(String),
    NamedSqlHook(String, Vec<(String, AuthoredValue)>),
    PythonHook(String, Vec<(String, AuthoredValue)>),
}

/// Whether a declaration reference names an enum member or a constant.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeclarationReferenceKind {
    Enum,
    Constant,
}

impl DeclarationReferenceKind {
    /// The reference keyword after `@`.
    #[must_use]
    pub const fn keyword(self) -> &'static str {
        match self {
            Self::Enum => "enum",
            Self::Constant => "const",
        }
    }
}

/// One `@enum("name").MEMBER` or `@const("name")` reference, with code-point offsets.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationReference {
    pub kind: DeclarationReferenceKind,
    pub name: String,
    pub member: Option<String>,
    pub start: usize,
    pub end: usize,
}

/// The error at which Python's `@enum`/`@const` expansion of a string stops.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeclarationReferenceStop {
    /// Quoted or dollar-quoted text before a later reference is never closed.
    UnclosedQuote,
    /// A block comment before a later reference is never closed.
    UnclosedBlockComment,
    /// `@enum` or `@const` starts a reference its full pattern does not match.
    Malformed(DeclarationReferenceKind),
}

/// The references Python resolves in a string, in order, and the error that ends its walk.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeclarationReferenceScan {
    pub references: Vec<DeclarationReference>,
    pub stop: Option<DeclarationReferenceStop>,
}

/// A header whose values nest deeper than the parser allows, located in its file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NestingFailure {
    /// The one-based file line of the container that exceeds the limit.
    pub line: usize,
    /// The syntax error, without a position.
    pub message: String,
    pub help: String,
}

/// One environment or context read made by SQL interpolation, in order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InterpolationRead {
    Environment(String),
    Context(String),
}

/// Interpolated SQL (`None` when unchanged), its code-point substitution spans and its reads.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InterpolatedSql {
    pub sql: Option<String>,
    pub spans: Vec<crate::compiler::types::CharSpan>,
    pub reads: Vec<InterpolationRead>,
}

/// The error interpolation stopped at, with the reads made before it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InterpolationFailure {
    pub message: String,
    pub reads: Vec<InterpolationRead>,
}
