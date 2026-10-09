//! The value plan of one macro call's arguments.

/// One argument value; Python builds the object, calling nested macros by their index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ArgumentValue {
    Str(String),
    /// An integer as its digits in `radix`, without underscores, for Python's unbounded `int`.
    Int {
        radix: u32,
        digits: String,
    },
    /// A float as Python's `float()` reads it, without underscores.
    Float(String),
    Bool(bool),
    None,
    /// The value of the nested macro call at this index of the call's nested spans.
    NestedCall(usize),
    /// A typed reference: the function (`__ref`, `__source` or `__seed`) and the resource name.
    TypedReference {
        function: String,
        name: String,
    },
    List(Vec<ArgumentValue>),
    Tuple(Vec<ArgumentValue>),
    /// Key and value pairs in source order; a later duplicate key replaces an earlier value.
    Dict(Vec<(ArgumentValue, ArgumentValue)>),
    /// Unary minus over a number, or over a nested call whose number Python checks.
    Negative(Box<ArgumentValue>),
    /// Unary plus, which leaves its number unchanged.
    Positive(Box<ArgumentValue>),
}

/// A call's parsed arguments and the typed references written in them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroArguments {
    pub positional: Vec<ArgumentValue>,
    pub keywords: Vec<(String, ArgumentValue)>,
    /// `(function, name)` of every typed reference, in Python's `ast.walk` order.
    pub typed_references: Vec<(String, String)>,
}
