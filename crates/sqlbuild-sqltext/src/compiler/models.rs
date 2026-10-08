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

/// A header whose values nest deeper than the parser allows, located in its file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NestingFailure {
    /// The one-based file line of the container that exceeds the limit.
    pub line: usize,
    /// The syntax error, without a position.
    pub message: String,
    pub help: String,
}
